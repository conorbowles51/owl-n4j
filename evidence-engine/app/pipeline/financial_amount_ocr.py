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


def _cleaned_line_readings(page, rect, rotation, deadline, language):
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
                                    config=f'--oem 1 --psm 7 --dpi {dpi} -c tessedit_char_whitelist=0123456789.,-+',
                                    timeout=min(5, remaining)).strip()
                            finally:
                                if oriented is not bordered:
                                    oriented.close()
                    observations.append(dict(dpi=dpi, segmentation_mode=7, text=value,
                        threshold=threshold, profile='cleaned_single_line'))
    return observations


def refine_credit_one_native_cells(page, tables, *, deadline, language):
    """Recover only missing card money from its original measured cell.

    A failed whole-page reread may drop a payment. This preserves every native
    row and only accepts independent crop consensus for an unreadable value;
    complete existing values and conflicting crop readings remain unchanged.
    """
    from dataclasses import replace
    from services.financial import pdf_tables
    from services.financial.statement_import_credit_one import credit_one_catalog, propose_credit_one_table
    from services.financial.statement_reading_quality import sources_from_tables, assess_statement_reading, prefer_image_reading
    if page.rotation or deadline - time.monotonic() < 2:
        return tables, []
    sources = sources_from_tables([table.to_json() for table in tables])
    cards, _ = credit_one_catalog(sources)
    if len(cards) != 1:
        return tables, []
    before = assess_statement_reading([table.to_json() for table in tables])
    if not before or not before['unreadable']:
        return tables, []
    replacements, records = {}, []
    deadline = min(deadline, time.monotonic() + 30)
    for source in sources:
        for row in propose_credit_one_table(source, 'USD', cards[0])['rows']:
            fields = row['fields']
            field = 'balance' if row['kind'] == 'balance' else 'amount_minor' if row['kind'] == 'transaction' else None
            column = fields.get('balance_column' if field == 'balance' else 'amount_column')
            if field is None or field in fields or column is None or deadline - time.monotonic() < 2:
                continue
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
                observations = _cleaned_line_readings(page, rect, 0, deadline, language)
            except (RuntimeError, pytesseract.TesseractError):
                continue
            valid = [o for o in observations if _money(o['text'])]
            if (len(observations) != 6 or not _money(observations[0]['text']) or len(valid) < 4
                    or len({o['dpi'] for o in valid}) != 2 or len({o['text'] for o in valid}) != 1):
                continue
            value = valid[0]['text']
            replacements[(source['table_index'], row['row_index'], int(column))] = value
            records.append(dict(method='tesseract_native_statement_cell_consensus', page=page.number + 1,
                table_index=source['table_index'], row_index=row['row_index'], column_index=int(column),
                field=field, original_text=cell['expected_text'], text=value, source_locator=locator,
                observations=observations, reason='unreadable_native_card_money'))
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
