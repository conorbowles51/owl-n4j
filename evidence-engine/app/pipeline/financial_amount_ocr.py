"""Reread damaged money cells on measured Andrews statement payment rows.

Amounts come from the source image, never from balancing arithmetic. Complete
matching visual readings are required; conflicting signs or digits stay flagged.
"""
from copy import deepcopy
from decimal import Decimal
import re
import time

import fitz
import pytesseract
from PIL import Image, ImageOps

from app.pipeline.ocr_geometry import project_ocr_words


def _money(text):
    return bool(re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}', text))


def _candidates(tables, words, width, height):
    candidates = []
    used = set()
    for table in tables:
        cells = table.to_json().get('table', {}).get('values', [])
        def box(cell):
            return cell.get('locator', {}).get('rect', [])
        def measured(cell):
            b = box(cell)
            return len(b) == 4 and all(type(v) is int for v in b) and b[0] < b[2] and b[1] < b[3]
        if not all(measured(c) for c in cells):
            continue
        # Require the bank and statement title in their printed header areas.
        if (not any(c['text'].strip() == 'Andrews' and box(c)[0] < width*.4
                    and box(c)[3] < height*.15 for c in cells)
                or not any(re.sub(r'\s+', '', c['text']) == 'AccountStatement'
                           and box(c)[0] > width*.4 and box(c)[3] < height*.15 for c in cells)):
            continue
        rows = {}
        for cell in cells:
            rows.setdefault(cell['row'], []).append(cell)
        for row in rows.values():
            row.sort(key=lambda c: c['column'])
            endpoint = _endpoint_balance_candidate(row, box, width, height, words, used)
            if endpoint:
                candidates.append(endpoint)
                continue
            if not 4 <= len(row) <= 8:
                continue
            descriptions = [c for c in row if re.match(r'^(?:Recurring\s+)?(?:Withdrawal|Deposit)\b', c['text'].strip())
                            and width*.08 < box(c)[0] < width*.25]
            if len(descriptions) != 1:
                continue
            description = descriptions[0]
            date_cells = row[:row.index(description)]
            money_cells = row[row.index(description)+1:]
            verb = re.match(r'^(?:Recurring\s+)?(Withdrawal|Deposit)\b', description['text'].strip())
            amounts = [c for c in money_cells if width*.46 <= box(c)[0] < box(c)[2] < width*.56]
            balances = [c for c in money_cells if width*.56 <= box(c)[0] < box(c)[2] <= width*.68]
            if (not verb or not date_cells or len(date_cells) > 3
                    or not 1 <= len(' '.join(c['text'].strip() for c in date_cells)) <= 12
                    or box(date_cells[0])[0] >= width*.08 or box(date_cells[0])[1] <= height*.2
                    or any(box(c)[2] >= box(description)[0] for c in date_cells)
                    or not amounts or not balances or len(amounts)+len(balances) != len(money_cells)
                    or box(description)[2] >= box(amounts[0])[0]
                    or any(box(a)[2] > box(b)[0] for a,b in zip(money_cells,money_cells[1:]))
                    or max(box(c)[1] for c in row) >= min(box(c)[3] for c in row)):
                continue
            for field, group in [('amount', amounts), ('balance', balances)]:
                text = ' '.join(c['text'].strip() for c in group)
                b = [min(box(c)[0] for c in group), min(box(c)[1] for c in group),
                     max(box(c)[2] for c in group), max(box(c)[3] for c in group)]
                readable = re.fullmatch(r'[+-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\s*\.\s*\d{2}', text)
                sign_conflict = False
                if readable and field == 'amount':
                    value = Decimal(re.sub(r'[\s,]', '', text))
                    sign_conflict = (value > 0 and verb[1] == 'Withdrawal'
                                     and 'Adjustment' not in description['text']
                                     or value < 0 and verb[1] == 'Deposit')
                # A missing minus can look like a valid positive amount, or
                # even an extra digit. Revisit the image only for an existing
                # description/sign conflict. The description never supplies
                # the replacement sign or amount; complete image readings do.
                if readable and not sign_conflict or len(text) > 24 or b[2]-b[0] > width*.13:
                    continue
                # All and only the words in this measured cell must agree with
                # its original text. Repeated text elsewhere is not a match.
                indices = sorted((i for i, w in enumerate(words)
                    if w[0]*1000 >= b[0]-1000 and w[1]*1000 >= b[1]-1000
                    and w[2]*1000 <= b[2]+1000 and w[3]*1000 <= b[3]+1000),
                    key=lambda i: words[i][0])
                if (not indices or len(indices) > 5 or used.intersection(indices)
                        or ' '.join(words[i][4] for i in indices) != ' '.join(text.split())):
                    continue
                used.update(indices)
                candidates.append(dict(indices=indices, text=text, rect=b, field=field,
                    verb=verb[1], adjustment='Adjustment' in description['text'],
                    reason='description_sign_conflict' if sign_conflict else 'unreadable_money'))
    return candidates[:40]


_ENDPOINT_LABEL = re.compile(r'(?:\S{4,7} ID \d{4} (?:BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT) Previous Balance'
                             r'|\S{4,7} Ending Balance)')


def _endpoint_balance_candidate(row, box, width, height, words, used):
    """Target an unreadable printed opening or ending balance cell.

    The exact printed label (Previous Balance on the share heading, or Ending
    Balance) must occupy the left of the line, and the line's only money cell
    must sit in the measured running-balance column. Nothing is computed from
    other balances; the crop reading must still agree with itself.
    """
    label = [c for c in row if box(c)[0] < width*.46]
    money = [c for c in row if box(c)[0] >= width*.46]
    if (not label or len(money) != 1 or len(row) > 10 or box(label[0])[0] >= width*.08
            or box(label[0])[1] <= height*.2
            or not _ENDPOINT_LABEL.fullmatch(' '.join(' '.join(c['text'].split()) for c in label))
            or max(box(c)[1] for c in row) >= min(box(c)[3] for c in row)):
        return None
    cell = money[0]
    b = list(box(cell))
    text = cell['text'].strip()
    if (_money(re.sub(r'\s+', '', text)) and re.fullmatch(r'[+-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\s*\.\s*\d{2}', text)
            or not (width*.56 <= b[0] < b[2] <= width*.68) or len(text) > 24 or b[2]-b[0] > width*.13):
        return None
    indices = sorted((i for i, w in enumerate(words)
        if w[0]*1000 >= b[0]-1000 and w[1]*1000 >= b[1]-1000
        and w[2]*1000 <= b[2]+1000 and w[3]*1000 <= b[3]+1000), key=lambda i: words[i][0])
    if (not indices or len(indices) > 5 or used.intersection(indices)
            or ' '.join(words[i][4] for i in indices) != ' '.join(text.split())):
        return None
    used.update(indices)
    return dict(indices=indices, text=text, rect=b, field='balance', verb=None, adjustment=False,
                reason='unreadable_endpoint_balance')


def _dollar_money(text):
    """A complete dollar amount as a card issuer prints it, e.g. ``- $40.00``."""
    return bool(re.fullmatch(r'(?:-\s?)?\$(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}', text))


def _cleaned_line_readings(page, rect, rotation, deadline, language, whitelist='0123456789.,-+'):
    """Read a measured money line at two sizes and three ink thresholds.

    Raw-line mode misreads signs on these small scanned cells. Use ordinary
    single-line segmentation for this profile; retain every result and refuse
    disagreement rather than taking a majority or calculating from balances.
    """
    clip = (fitz.Rect([v / 1000 for v in rect]) + (-3, -1, 3, 1)) & page.rect
    observations = []
    for dpi in (300, 450):
        if deadline - time.monotonic() < 2:
            break
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip,
            colorspace=fitz.csRGB, alpha=False, annots=True)
        with Image.frombytes('RGB', (pix.width, pix.height), pix.samples) as raw:
            with raw.convert('L') as grey:
                for threshold in (150, 190, 220):
                    remaining = deadline - time.monotonic()
                    if remaining < 1:
                        break
                    with grey.point(lambda value: 255 if value >= threshold else 0) as ink:
                        with ImageOps.expand(ink, border=15, fill=255) as bordered:
                            oriented = bordered.rotate(-rotation, expand=True, fillcolor=255) if rotation else bordered
                            try:
                                value = pytesseract.image_to_string(oriented, lang=language,
                                    config=f'--oem 1 --psm 7 --dpi {dpi} -c tessedit_char_whitelist={whitelist}',
                                    timeout=min(5, remaining)).strip()
                            finally:
                                if oriented is not bordered:
                                    oriented.close()
                    observations.append(dict(dpi=dpi, segmentation_mode=7, text=value,
                        threshold=threshold, profile='cleaned_single_line'))
    return observations


def refine_statement_native_cells(page, tables, *, deadline, language):
    """Recover missing statement money from its original measured cell.

    A failed whole-page reread may drop a payment. This preserves every native
    row and only accepts repeated crop agreement for an unreadable value;
    complete existing values and conflicting crop readings remain unchanged.
    """
    from dataclasses import replace
    from services.financial import pdf_tables
    from services.financial.statement_import_credit_one import credit_one_catalog, propose_credit_one_table
    from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
    from services.financial.statement_import_andrews import andrews_page, propose_andrews_statement
    from services.financial.statement_reading_quality import (sources_from_tables, assess_statement_reading,
        prefer_image_reading, labelled_statement, propose_labelled_rows, bbva_page_statement, capital_one_page_statement)
    if page.rotation or deadline - time.monotonic() < 2:
        return tables, []
    sources = sources_from_tables([table.to_json() for table in tables])
    if not sources:
        return tables, []
    cards, _ = credit_one_catalog(sources)
    merrick = merrick_statement(sources[0]) if len(sources) == 1 else None
    labelled = None
    # Layouts whose rows name their money column per row rather than one
    # amount column: (field, column key) pairs to try for a payment row.
    payment_columns = None
    # How a complete reading of the cell must look, and the characters the
    # reread may produce. Card amounts print their dollar sign inside the
    # cell, so it must be readable there rather than taken for a digit.
    valid_money, whitelist = _money, '0123456789.,-+'
    if len(cards) == 1:
        propose = lambda source: propose_credit_one_table(source, 'USD', cards[0])
    elif (bbva := bbva_page_statement(sources)) is not None:
        # The Cargos or Abonos column holding the payment's only amount.
        rows = bbva[1]
        propose = lambda source: dict(rows=[r for r in rows if r['table_index'] == source['table_index']])
        payment_columns = [('amount_minor', 'debit_column'), ('amount_minor', 'credit_column'), ('balance', 'balance_column')]
    elif (capital := capital_one_page_statement(sources)) is not None:
        # The printed Amount column cited by the card layout for that row.
        rows = [{**r, 'fields': {**r['fields'], 'amount_column': str(r['layout_context']['amount_source']['column_index'])}}
                if (r.get('layout_context') or {}).get('amount_source') else r for r in capital[1]]
        propose = lambda source: dict(rows=[r for r in rows if r['table_index'] == source['table_index']])
        valid_money, whitelist = _dollar_money, '0123456789.,-+$'
    elif merrick:
        propose = lambda source: propose_merrick_table(source, 'USD', merrick)
    elif (labelled := None if any(andrews_page(s, allow_unbranded=True) for s in sources)
            else labelled_statement(sources)):
        # Labelled columns name the money they hold; an unreadable credit or
        # debit stays in that column, so the target is that printed cell.
        rows = propose_labelled_rows(sources, labelled)
        propose = lambda source: dict(rows=[r for r in rows if r['table_index'] == source['table_index']])
    else:
        andrews = andrews_page(sources[0], allow_unbranded=True) if len(sources) == 1 else None
        if not andrews:
            return tables, []
        scope = dict(page_number=sources[0]['page_number'], table_index=sources[0]['table_index'],
            heading_rows=andrews['heading_rows'], row_indices=[r['row_index'] for r in sources[0]['rows']
                if r['row_index'] >= andrews['body_start']])
        statement = dict(period_start=andrews['start'], period_end=andrews['end'], sources=[scope])
        propose = lambda source: propose_andrews_statement([source], 'USD', statement)
    before = assess_statement_reading([table.to_json() for table in tables])
    if not before or not before['unreadable']:
        return tables, []
    replacements, records = {}, []
    deadline = min(deadline, time.monotonic() + 30)
    targets = []
    for source in sources:
        for row in propose(source)['rows']:
            fields = row['fields']
            payment = row['kind'] in ('transaction', 'unresolved') and not row['excluded']
            candidates = [('balance', 'balance_column')] if row['kind'] == 'balance' else (
                [('credit', 'credit_column'), ('debit', 'debit_column'), ('amount', 'amount_column'),
                 ('balance', 'balance_column')] if labelled and payment else
                payment_columns if payment and payment_columns else
                [('amount_minor', 'amount_column'), ('balance', 'balance_column')] if payment else [])
            if (row['kind'] == 'balance' and fields.get('statement_layout') == 'andrews-share-statement'
                    and sum(1 for c in row['source_cells'] if (c.get('locator') or {}).get('rect')
                            and c['locator']['rect'][0] >= page.rect.width * 1000 * .46) != 1):
                # A balance split across several money cells is not one
                # measured target; a fragment could read as a complete value.
                candidates = []
            for field, column_key in candidates:
                column = fields.get(column_key)
                if field not in fields and column is not None:
                    targets.append((source, row, field, column))
    for source, row, field, column in targets:
        if deadline - time.monotonic() < 2:
            break
        matches = [c for c in row['source_cells'] if str(c['column_index']) == column]
        if len(matches) != 1:
            continue
        cell = matches[0]
        locator = cell.get('locator') or {}
        rect = locator.get('rect') or []
        size = locator.get('page_size') or []
        if (locator.get('kind') != 'page_rectangle' or locator.get('page') != page.number + 1
                or len(rect) != 4 or len(size) != 2 or not all(type(v) is int for v in rect + size)
                or not 0 <= rect[0] < rect[2] <= size[0] or not 0 <= rect[1] < rect[3] <= size[1]
                or abs(size[0] - page.rect.width * 1000) > 2 or abs(size[1] - page.rect.height * 1000) > 2
                or rect[2] - rect[0] > size[0] * .13 or len(cell['expected_text']) > 24):
            continue
        try:
            observations = _cleaned_line_readings(page, rect, 0, deadline, language, whitelist)
        except (RuntimeError, pytesseract.TesseractError):
            continue
        valid = [o for o in observations if valid_money(o['text'])]
        if (len(observations) != 6 or not valid_money(observations[0]['text']) or len(valid) < 4
                or len({o['dpi'] for o in valid}) != 2 or len({o['text'] for o in valid}) != 1):
            continue
        value = valid[0]['text']
        if valid_money is _dollar_money and value.startswith('-') != cell['expected_text'].strip().startswith('-'):
            # The printed sign decides payment or purchase; the reread may
            # only supply the digits the page reading lost, never the sign.
            continue
        replacements[(source['table_index'], row['row_index'], int(column))] = value
        records.append(dict(method='tesseract_native_statement_cell_consensus', page=page.number + 1,
            table_index=source['table_index'], row_index=row['row_index'], column_index=int(column),
            field=field, original_text=cell['expected_text'], text=value, source_locator=locator,
            observations=observations, reason='unreadable_native_statement_money'))
    if not replacements:
        return tables, []
    refined = []
    for index, table in enumerate(tables):
        if table.geometry is None:
            return tables, []
        cells = tuple(replace(cell, text=replacements.get((index, cell.row, cell.column), cell.text))
            for cell in table.geometry.cells)
        rows = {}
        for cell in cells:
            rows.setdefault(cell.row, {})[cell.column] = cell.text
        grid = [[row.get(column, '') for column in range(max(row) + 1)] for _, row in sorted(rows.items())]
        chunk = pdf_tables._chunk(grid, page.number + 1)
        if not chunk:
            return tables, []
        refined.append(replace(table, geometry=replace(table.geometry, cells=cells), chunk=chunk))
    after = assess_statement_reading([table.to_json() for table in refined])
    if not prefer_image_reading(before, after):
        return tables, []
    for record in records:
        record.update(original_quality=before, refined_quality=after)
    return refined, records


# Compatibility for callers of the earlier layout-specific entry point.
refine_credit_one_native_cells = refine_statement_native_cells


def reread_financial_amounts(page, data, *, rotation, image_width, image_height,
                             reader, deadline, language):
    page_text = ' '.join(text.strip() for text in data['text'] if text.strip())
    if (reader is None or 'Andrews' not in page_text or 'Account Statement' not in page_text
            or deadline-time.monotonic() < 2):
        return data, []
    words = project_ocr_words(data, rotation=rotation, image_width=image_width,
        image_height=image_height, page_width=page.rect.width, page_height=page.rect.height)
    tables = reader.read_positioned_ocr_words(words, page_number=page.number+1,
        page_width=page.rect.width, page_height=page.rect.height)
    indices = [i for i, text in enumerate(data['text']) if text.strip()]
    result, records = data, []
    deadline = min(deadline, time.monotonic()+30)
    for candidate in _candidates(tables, words, page.rect.width*1000, page.rect.height*1000):
        if deadline-time.monotonic() < 2:
            break
        original_words = [words[i] for i in candidate['indices']]
        b = candidate['rect']
        clip = (fitz.Rect([v/1000 for v in b])+(-2,-2,2,2)) & page.rect
        if clip.is_empty or clip.width*clip.height*100 > 1_000_000:
            continue
        observations = []
        try:
            cleaned = _cleaned_line_readings(page, b, rotation, deadline, language)
            clean_valid = [o for o in cleaned if _money(o['text'])]
            if len({o['text'] for o in clean_valid}) > 1:
                continue
            clean_agrees = (len(cleaned) == 6 and _money(cleaned[0]['text'])
                and len(clean_valid) >= 4 and len({o['dpi'] for o in clean_valid}) == 2)
            if clean_agrees:
                observations = cleaned
                valid = [o['text'] for o in clean_valid]
                original_agrees = False
            else:
                for dpi in (720, 600):
                    if dpi == 600:
                        valid = [o['text'] for o in observations if _money(o['text'])]
                        if len(valid) != 1 or not _money(observations[0]['text']):
                            break
                    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72), clip=clip,
                        colorspace=fitz.csRGB, alpha=False, annots=True)
                    image = Image.frombytes('RGB', (pix.width,pix.height),pix.samples)
                    try:
                        if rotation:
                            oriented = image.rotate(-rotation,expand=True,fillcolor='white')
                            image.close()
                            image = oriented
                        for mode in (7,13):
                            remaining = deadline-time.monotonic()
                            if remaining < 1:
                                break
                            text = pytesseract.image_to_string(image,lang=language,
                                config=f'--oem 1 --psm {mode} --dpi {dpi} -c tessedit_char_whitelist=0123456789.,-+',
                                timeout=min(10,remaining)).strip()
                            observations.append(dict(dpi=dpi,segmentation_mode=mode,text=text))
                    finally:
                        image.close()
                valid = [o['text'] for o in observations if _money(o['text'])]
                original_agrees = (bool(observations) and _money(observations[0]['text'])
                                   and len(valid) >= 2 and len(set(valid)) == 1)
                if not original_agrees:
                    if len(set(valid)) > 1:
                        continue
                    # Oversized glyphs can fragment on small scanned money cells.
                    # Try a compact crop with a white border. Keep every earlier
                    # valid reading: no alternate profile can outvote a conflict.
                    compact = []
                    compact_clip = (fitz.Rect([v/1000 for v in b])+(-2,-1,2,1)) & page.rect
                    for dpi in (300,450):
                        if deadline-time.monotonic() < 2:
                            break
                        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),clip=compact_clip,
                            colorspace=fitz.csRGB,alpha=False,annots=True)
                        with Image.frombytes('RGB',(pix.width,pix.height),pix.samples) as raw:
                            with ImageOps.expand(raw,border=10,fill='white') as image:
                                if rotation:
                                    oriented=image.rotate(-rotation,expand=True,fillcolor='white')
                                else:
                                    oriented=image
                                try:
                                    for mode in (7,13):
                                        remaining=deadline-time.monotonic()
                                        if remaining < 1:
                                            break
                                        value=pytesseract.image_to_string(oriented,lang=language,
                                            config=f'--oem 1 --psm {mode} --dpi {dpi} -c tessedit_char_whitelist=0123456789.,-+',
                                            timeout=min(10,remaining)).strip()
                                        compact.append(dict(dpi=dpi,segmentation_mode=mode,text=value,profile='compact_white_border'))
                                finally:
                                    if oriented is not image:
                                        oriented.close()
                    observations.extend(compact)
                    compact_valid=[o['text'] for o in compact if _money(o['text'])]
                    valid=[o['text'] for o in observations if _money(o['text'])]
                    if (len(compact) != 4 or not _money(compact[0]['text'])
                            or len(compact_valid) < 2 or len(set(valid)) != 1):
                        continue
                # Older crop profiles may help an incomplete line reading,
                # but cannot override any complete result from that reading.
                observations = cleaned + observations
                valid = [o['text'] for o in observations if _money(o['text'])]
                if len(set(valid)) != 1:
                    continue
            text = valid[0]
            # An image reading that loses a withdrawal sign is not acceptable.
            # Adjustment credits may legitimately be positive. No sign is added.
            if candidate['field'] == 'amount' and (
                    candidate['verb'] == 'Withdrawal' and not candidate['adjustment'] and not text.startswith('-')
                    or candidate['verb'] == 'Deposit' and text.startswith('-')):
                continue
            if result is data:
                result = deepcopy(data)
            raw_indices = [indices[i] for i in candidate['indices']]
            first = raw_indices[0]
            # Keep the union of the original OCR rectangles when a damaged
            # money cell had been split into words. Other cells stay untouched.
            left = min(data['left'][i] for i in raw_indices)
            top = min(data['top'][i] for i in raw_indices)
            right = max(data['left'][i]+data['width'][i] for i in raw_indices)
            bottom = max(data['top'][i]+data['height'][i] for i in raw_indices)
            for key, value in dict(left=left,top=top,width=right-left,height=bottom-top,text=text).items():
                result[key][first] = value
            for i in raw_indices[1:]:
                result['text'][i] = ''
            records.append(dict(method='tesseract_amount_crop_consensus',page=page.number+1,
                rect=b,field=candidate['field'],original_text=candidate['text'],text=text,
                reason=candidate['reason'],
                original_words=[dict(text=w[4],rect=[round(v*1000) for v in w[:4]]) for w in original_words],
                dpi=720 if original_agrees else 300,
                segmentation_modes=[7] if clean_agrees else [7,13],
                profile='cleaned_single_line' if clean_agrees else 'original_or_compact',
                character_set='0123456789.,-+',observations=observations))
        except (RuntimeError,pytesseract.TesseractError):
            continue
    return result, records
