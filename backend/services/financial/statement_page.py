"""The statement page a payment was read from, for naming it beside the Transactions table.

A person naming a payment needs to see its line on the statement, and the lines just above and below it, because the
name is often printed on the next line or at the top of the next page. This module answers two questions for one
payment of one case, and nothing else:

* :func:`payment_page`: which page the payment sits on, how many pages the file has, the stored locator, whether the
  payment is the last one read on its page (so the next page's top is worth showing), and, when the locator only
  knows the page, where the payment's amount and date are printed on that page's text layer.
* :func:`payment_page_png`: that page, or the page just before or after it, rendered as the image the stored
  rectangle refers to (``page_render``).

Both resolve the payment through ``ledger_source``, which refuses a payment, statement or evidence file of another
case and a file whose digest no longer matches the reading, so a caller can never reach a page of a file the case
does not hold. Neither writes anything.

Found positions are suggestions to look at, never a stored locator: a page-only payment keeps its page-only locator.
A printed figure that also appears on another line (a running balance equal to the amount, say) is returned once per
place it is printed, so the person sees every candidate rather than one guessed line.
"""
from __future__ import annotations

import re
from datetime import date
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from services.financial.ledger_source import LedgerSourceError, ledger_source
from services.financial.page_render import PageRenderError, render_page_png
from services.financial.transactions import LOCATOR_PROVENANCE_KEY

_MONTHS = {
    1: ('ENE', 'JAN'), 2: ('FEB',), 3: ('MAR',), 4: ('ABR', 'APR'), 5: ('MAY',), 6: ('JUN',), 7: ('JUL',),
    8: ('AGO', 'AUG'), 9: ('SEP', 'SEPT'), 10: ('OCT',), 11: ('NOV',), 12: ('DIC', 'DEC'),
}
# A printed amount carries a currency sign, a sign or a CR/DR mark around the figure; none of them changes the figure.
_AMOUNT_EDGES = re.compile(r'^[\s$€£(+\-]*(?:MXN|USD|MN)?[\s$]*|[\s)\-+*]*(?:CR|DR|MN)?[\s)\-+*]*$', re.I)


def _resolve(session, case_id, transaction_id):
    """The payment's same-case source, or LedgerSourceError (404 for another case's payment or file)."""
    return ledger_source(session, case_id=case_id, transaction_id=transaction_id)


def _open(session, case_id, source, *, resolve_path, open_pdf):
    record = session.scalar(select(EvidenceFile).where(EvidenceFile.id == UUID(source['evidence_file_id']),
                                                       EvidenceFile.case_id == case_id))
    path = resolve_path(record.stored_path) if record is not None else None
    if path is None or not path.exists():
        raise LedgerSourceError('The statement file is not available on this server.', 404)
    if path.suffix.lower() != '.pdf':
        raise LedgerSourceError('The statement file is not a PDF, so there is no page to show.', 422)
    try:
        return open_pdf(path)
    except Exception as exc:  # noqa: BLE001 - any library failure is the same answer to the person
        raise LedgerSourceError('The statement file could not be opened as a PDF.', 422) from exc


def _amount_texts(amount_minor, currency):
    """The ways a statement prints this amount: 1,234.56 / 1234.56 / 1.234,56 / 1234,56."""
    from services.financial.money import get_currency
    try:
        exponent = get_currency(currency).exponent
    except Exception:  # noqa: BLE001 - an unknown currency is searched as two decimals, the common case
        exponent = 2
    whole, cents = divmod(abs(int(amount_minor)), 10 ** exponent)
    grouped = f'{whole:,}'
    if not exponent:
        return {grouped, str(whole), grouped.replace(',', '.')}
    tail = str(cents).zfill(exponent)
    return {f'{grouped}.{tail}', f'{whole}.{tail}', f"{grouped.replace(',', '.')},{tail}", f'{whole},{tail}'}


def _date_texts(day: date):
    """Single printed words for this date: 15/01, 01/15, 15/01/24, 2024-01-15, 15-ENE, 15ENE, JAN15 …"""
    d, m, y = day.day, day.month, day.year
    texts = set()
    for dd in {f'{d:02d}', str(d)}:
        for mm in {f'{m:02d}', str(m)}:
            for sep in '/-.':
                texts |= {f'{dd}{sep}{mm}', f'{mm}{sep}{dd}'}
                for yy in (str(y), f'{y % 100:02d}'):
                    texts |= {f'{dd}{sep}{mm}{sep}{yy}', f'{mm}{sep}{dd}{sep}{yy}'}
        for name in _MONTHS[m]:
            texts |= {f'{dd}{name}', f'{dd}-{name}', f'{dd}/{name}', f'{name}{dd}', f'{name}-{dd}', f'{name}/{dd}'}
    texts.add(day.isoformat())
    return {text.upper() for text in texts}


def _two_word_dates(day: date):
    """Dates printed as two words: '15 ENE' or 'JAN 15'."""
    pairs = set()
    for dd in {f'{day.day:02d}', str(day.day)}:
        for name in _MONTHS[day.month]:
            pairs |= {(dd, name), (name, dd)}
    return pairs


def find_on_page(page, *, amount_minor, currency, dates):
    """Where the amount and the dates are printed on ``page``'s text layer, as fractions of the displayed page.

    ``page`` is fitz-Page-shaped: ``rect`` and ``get_text('words')`` tuples (x0, y0, x1, y1, word, block, line, n).
    A page with no text layer (a scan) returns no words and so finds nothing; that is reported, not guessed around.
    """
    width, height = float(page.rect.width), float(page.rect.height)
    words = [w for w in page.get_text('words') if str(w[4]).strip()]
    amounts = _amount_texts(amount_minor, currency)
    singles = set().union(*(_date_texts(d) for d in dates)) if dates else set()
    doubles = set().union(*(_two_word_dates(d) for d in dates)) if dates else set()
    found = []

    def box(x0, y0, x1, y1):
        return [round(x0 / width, 5), round(y0 / height, 5), round(x1 / width, 5), round(y1 / height, 5)]

    for index, word in enumerate(words):
        x0, y0, x1, y1, text = word[:5]
        text = str(text)
        figure = _AMOUNT_EDGES.sub('', text)
        if figure in amounts:
            found.append(dict(kind='amount', text=text, rect=box(x0, y0, x1, y1)))
            continue
        token = text.strip('.,;:()').upper()
        if token in singles:
            found.append(dict(kind='date', text=text, rect=box(x0, y0, x1, y1)))
            continue
        following = words[index + 1] if index + 1 < len(words) else None
        if following is not None and tuple(following[5:7]) == tuple(word[5:7]):
            pair = (token, str(following[4]).strip('.,;:()').upper())
            if pair in doubles:
                found.append(dict(kind='date', text=f'{text} {following[4]}',
                                  rect=box(x0, min(y0, following[1]), following[2], max(y1, following[3]))))
    return dict(found=found, text_layer=bool(words))


def _last_on_page(session, case_id, transaction_id, locator):
    """True when no other payment of the same statement file was read lower on the same page."""
    row = session.get(FinancialTransaction, transaction_id)
    if row is None or locator.get('kind') != 'page_rectangle':
        return None
    bottom = locator['rect'][3]
    others = session.scalars(select(FinancialTransaction.provenance).where(
        FinancialTransaction.case_id == case_id, FinancialTransaction.source_document_id == row.source_document_id,
        FinancialTransaction.id != row.id, FinancialTransaction.ledger_status == 'admitted',
        FinancialTransaction.superseded_by_id.is_(None)))
    for provenance in others:
        other = (provenance or {}).get(LOCATOR_PROVENANCE_KEY) if isinstance(provenance, dict) else None
        if (isinstance(other, dict) and other.get('kind') == 'page_rectangle' and other.get('page') == locator['page']
                and isinstance(other.get('rect'), list) and len(other['rect']) == 4 and other['rect'][3] > bottom):
            return False
    return True


def payment_page(session, *, case_id, transaction_id, resolve_path, open_pdf):
    """Where this payment is printed: page, page count, locator, last-on-page, and found amount/date for page-only."""
    source = _resolve(session, case_id, transaction_id)
    locator = source['locator'] if source['locator_state'] == 'stored' else None
    page = locator.get('page') if locator else None
    result = dict(case_id=str(case_id), transaction_id=str(transaction_id),
                  evidence_file_id=source['evidence_file_id'], filename=source['filename'],
                  locator=locator, locator_state=source['locator_state'], page=page, page_count=None,
                  last_on_page=None, found=[], text_layer=None)
    if page is None:
        return result
    document = _open(session, case_id, source, resolve_path=resolve_path, open_pdf=open_pdf)
    try:
        result['page_count'] = document.page_count
        if page > document.page_count:
            raise LedgerSourceError('The stored page is beyond the end of the statement file.', 409)
        result['last_on_page'] = _last_on_page(session, case_id, transaction_id, locator)
        if locator['kind'] == 'page_only':
            view = source['transaction']
            dates = sorted({date.fromisoformat(str(view[key])[:10]) for key in
                            ('transaction_date', 'posted_date', 'value_date', 'ordering_date') if view.get(key)})
            result.update(find_on_page(document.load_page(page - 1), amount_minor=view['amount_minor'],
                                       currency=view['currency'], dates=dates))
    finally:
        document.close()
    return result


def payment_page_png(session, *, case_id, transaction_id, page, width, resolve_path, open_pdf):
    """The payment's page, or the page just before or after it, as a PNG ``width`` pixels wide."""
    source = _resolve(session, case_id, transaction_id)
    locator = source['locator'] if source['locator_state'] == 'stored' else None
    stored = locator.get('page') if locator else None
    if stored is None:
        raise LedgerSourceError('No page is stored for this payment. Open the statement file instead.', 404)
    if page not in (stored - 1, stored, stored + 1):
        raise LedgerSourceError('Only the payment’s own page and the pages next to it can be shown here.', 422)
    document = _open(session, case_id, source, resolve_path=resolve_path, open_pdf=open_pdf)
    try:
        return render_page_png(document, page_number=page, width=width), document.page_count
    except PageRenderError as exc:
        raise LedgerSourceError(str(exc), 404) from exc
    finally:
        document.close()
