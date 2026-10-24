"""Fund statements: documents that list holdings, not money in and out of an account.

An investment-fund statement ("ESTADO DE CUENTA / FONDOS DE INVERSIÓN") reports the fund units an account
holds, their price and market value, and the unit purchases and sales of the period. The cash of those
purchases and sales moves through the associated bank account, whose own statement carries it. Read as a
payment statement it can never reconcile (no opening and closing cash balance), so it waited in the queue
for an investigator with nothing she could fix, and saving its rows would count the linked account's money
a second time.

A statement is recognised as a fund statement only when the page evidence is clear (fail closed):

* at least one of its pages prints the fund-statement title, and one of those pages prints the holdings
  table (units, price, market value);
* every row the reading took from the statement's pages (a payment, a balance, a total, an unread line
  with an amount, balance or date) sits on a page printing that title: a page of any other kind of
  statement in the reading keeps its normal review. A reader's own note (the period it could not prove)
  is not printed money;
* the reading has no payment: a statement whose reading has a movement ledger keeps that ledger and its
  ordinary readiness, whatever its pages print;
* nobody saved a review of it, it is not imported, and no person put it back.

It is then set aside as "not a payment statement": out of the waiting queue, never saveable (the import
writer refuses it), its reading, evidence and rows untouched. The reason is shown, and a person can put it
back for review (``decide``), which is recorded on the file and is final for that statement until the
person sets it aside again. Nothing is deleted.

Switch: LOUPE_FINANCIAL_NOT_PAYMENT_STATEMENTS (default on). Off: fund statements are read and held as
before; any recorded decision is ignored.
"""
import os
import re
from copy import deepcopy
from datetime import datetime, timezone

ENABLED = os.environ.get('LOUPE_FINANCIAL_NOT_PAYMENT_STATEMENTS', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
# On the file's metadata: the readiness guards digest every "statement_" key, so a decision makes the
# stored readiness of the file's statements stale.
METADATA_KEY = 'statement_not_payment_decisions'
KIND = 'fund_holdings'
REASON = ('This is an investment-fund statement: it lists the fund units held, their price and market value. '
          'It has no account payments to import. The cash of its purchases and sales is on the linked account\'s '
          'own statement. Set aside; the PDF and its reading are kept.')
LABEL = 'Not a payment statement'
TITLE = re.compile(r'ESTADO\s+DE\s+CUENTA\s+FONDOS\s+DE\s+INVERSI[OÓ0]N', re.I)
HOLDINGS = (re.compile(r'T[IÍ]TULOS', re.I), re.compile(r'PRECIO', re.I), re.compile(r'VALOR\s+DE\s+MERCADO', re.I))
# Rows a reading takes from a statement's money. Header rows are the page furniture the reader set aside.
MONEY_KINDS = ('transaction', 'balance', 'statement_total', 'total', 'unresolved', 'unclassified')


def page_texts(content, locations):
    """{page number: text} from a reading's page locations."""
    pages = {}
    for location in locations or []:
        if isinstance(location, dict) and location.get('kind') == 'page' and isinstance(location.get('page_number'), int):
            start, end = location.get('start_char'), location.get('end_char')
            if isinstance(start, int) and isinstance(end, int):
                pages[location['page_number']] = pages.get(location['page_number'], '') + (content or '')[start:end]
    return pages


def fund_pages(pages):
    """(title pages, holdings pages) of a reading's page texts."""
    title = {number for number, text in pages.items() if TITLE.search(text or '')}
    holdings = {number for number in title if all(pattern.search(pages[number]) for pattern in HOLDINGS)}
    return title, holdings


def decision(file, statement_id):
    if not ENABLED or file is None:
        return None
    value = ((file.metadata_ or {}).get(METADATA_KEY) or {}).get(statement_id or '')
    return value if isinstance(value, dict) else None


def classify(file, text, proposal):
    """The set-aside of one statement reading, or None. Read only.

    ``proposal`` is the statement's reading (read_statement_import). None unless every rule of the
    module docstring holds.
    """
    if not ENABLED or text is None or not proposal or proposal.get('current_import') or proposal.get('saved_review'):
        return None
    if proposal.get('document_review') or proposal.get('assignment_only'):
        return None
    recorded = decision(file, proposal.get('statement_id'))
    if recorded and recorded.get('status') == 'restored':
        return None
    rows = proposal.get('rows') or []
    if any(row.get('kind') == 'transaction' and not row.get('excluded') for row in rows):
        return None  # a movement ledger: it keeps its reading and readiness
    # A reader's own note (the period it could not prove) is not printed money: it carries no amount, balance
    # or date, and is placed on the statement's first page whatever that page prints.
    money = [row for row in rows if row.get('kind') in MONEY_KINDS and any(
        (row.get('fields') or {}).get(key) not in (None, '') for key in ('amount_minor', 'balance', 'date', 'booking_date', 'value_date'))]
    notes = [row for row in rows if row.get('kind') in MONEY_KINDS and row not in money]
    pages = page_texts(text.content, text.source_locations)
    statement_pages = set(proposal.get('statement_page_numbers') or proposal.get('page_numbers') or [])
    pages = {number: value for number, value in pages.items() if not statement_pages or number in statement_pages}
    title, holdings = fund_pages(pages)
    if not title or not holdings:
        return None
    if any(row.get('page_number') not in title for row in money):
        return None  # a row read from a page of another kind: not proven to be the fund statement
    return dict(kind=KIND, status='set_aside', label=LABEL, reason=REASON,
                evidence=dict(title_pages=sorted(title), holdings_pages=sorted(holdings),
                              statement_pages=sorted(statement_pages), payments=0, unread_rows=sum(
                                  row.get('kind') in ('unresolved', 'unclassified') for row in money),
                              reader_notes=len(notes)),
                **({'decided_by': recorded.get('actor')} if recorded else {}))


def _persist(file, statement_id, status, actor, reason):
    metadata = deepcopy(file.metadata_ or {})
    decisions = metadata.setdefault(METADATA_KEY, {})
    previous = decisions.get(statement_id or '')
    history = deepcopy((previous or {}).get('history', []))
    if previous:
        history.append({key: value for key, value in previous.items() if key != 'history'})
    decisions[statement_id or ''] = dict(status=status, reason=reason, at=datetime.now(timezone.utc).isoformat(),
        actor=dict(user_id=str(actor.user_id), name=actor.name) if actor else dict(name='System'), history=history)
    file.metadata_ = metadata


def decide(session, *, case_id, evidence_file_id, statement_id=None, action, actor=None, reason=''):
    """Put a set-aside fund statement back for review ('restore'), or set it aside again ('set_aside').

    Recorded on the file (with history); the statement's batch items are assessed again at once. Commits.
    """
    from sqlalchemy import select
    from postgres.models.case import Case
    from postgres.models.evidence import EvidenceFile
    from services.financial.pdf_candidates import PdfMappingError
    if action not in ('restore', 'set_aside'):
        raise PdfMappingError('Unknown action.', 422)
    if not ENABLED:
        raise PdfMappingError('Setting aside statements that are not payment statements is switched off.', 409)
    if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
        raise PdfMappingError('Case not found.', 404)
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    if action == 'restore':
        _persist(file, statement_id, 'restored', actor, reason.strip() or 'Put back for review by the investigator.')
    else:
        _persist(file, statement_id, 'set_aside', actor, reason.strip() or 'Set aside again by the investigator.')
    session.flush()
    from services.financial.statement_import import read_statement_import
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id, statement_id=statement_id,
                                     _include_duplicate_disposition=False)
    if action == 'set_aside' and not proposal.get('not_payment_statement'):
        raise PdfMappingError('This statement does not show the pages of a fund statement; it stays in review.', 409)
    reassess_items(session, case_id, file.id, statement_id or '', proposal)
    session.commit()
    from services.financial.import_batches import refresh_file_readiness
    refresh_file_readiness(session, case_id=case_id, file_id=file.id, statement_key=statement_id or '')
    return dict(case_id=str(case_id), evidence_file_id=str(file.id), statement_id=statement_id,
                not_payment_statement=proposal.get('not_payment_statement'),
                decision={key: value for key, value in (decision(file, statement_id) or {}).items() if key != 'history'})


def reassess_items(session, case_id, file_id, statement_key, proposal):
    """Bring the held batch items of one statement in line with its reading's set-aside. Returns how many changed."""
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial.import_batches import assess
    changed = 0
    for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
            Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == file_id,
            Item.statement_key == statement_key, Item.status.in_(('ready', 'attention')))):
        if item.review_request and proposal.get('not_payment_statement'):
            continue  # a person's draft on a held statement is not set aside by this pass
        state, summary = assess(proposal, item.review_request)
        merged = {key: value for key, value in (item.summary or {}).items() if key != 'not_payment_statement'}
        merged.update(summary)
        if state != item.status or merged != item.summary:
            item.status, item.summary = state, merged
            changed += 1
    session.flush()
    return changed
