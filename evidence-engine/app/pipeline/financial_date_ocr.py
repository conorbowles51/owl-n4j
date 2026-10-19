"""A bounded second visual reading of unclear dates in a known printed grid.

This rereads pixels, never substitutes characters or derives dates from money.
It leaves disagreements unchanged and retains each successful reading's input.
"""
from copy import deepcopy
from datetime import date
import re
import time

import fitz
import pytesseract
from PIL import Image

from app.pipeline.ocr_geometry import project_ocr_words


def _date_text(text):
    match = re.fullmatch(r'(\d{1,2})/(\d{1,2})(?:/(\d{2}|20\d{2}))?', text)
    if not match:
        return False
    try:
        year = int(match[3]) if match[3] else 2000
        date(year + 2000 if year < 100 else year, int(match[1]), int(match[2]))
        return True
    except ValueError:
        return False


def _full_date(text):
    if not re.fullmatch(r'\d{2}/\d{2}/(?:20)?\d{2}', text) or not _date_text(text):
        return None
    month, day, year = map(int, text.split('/'))
    return date(year + 2000 if year < 100 else year, month, day)


def _andrews_headings(tables, width, height):
    """Yield one measured account/period heading under the printed bank/title."""
    for table in tables:
        values = table.to_json().get('table', {}).get('values', [])
        top = [c for c in values if len(c.get('locator', {}).get('rect', [])) == 4
               and c['locator']['rect'][3] < height * 200]
        marks = [c for c in top if c['text'].strip() == 'Andrews'
                 and c['locator']['rect'][0] < width * 400 and c['locator']['rect'][3] < height * 150]
        titles = [c for c in top if re.sub(r'\s+', '', c['text']) == 'AccountStatement'
                  and c['locator']['rect'][0] > width * 400 and c['locator']['rect'][3] < height * 150]
        accounts = [c for c in top if re.fullmatch(r'\d{9}', c['text'].strip())
                    and c['locator']['rect'][0] > width * 400]
        if len(marks) != 1 or len(titles) != 1 or len(accounts) != 1:
            continue
        rows = {}
        for cell in top:
            rows.setdefault(cell['row'], []).append(cell)
        pairs = []
        for cells in rows.values():
            cells.sort(key=lambda c: c['column'])
            if len(cells) != 2:
                continue
            boxes = [c['locator']['rect'] for c in cells]
            texts = [c['text'].strip() for c in cells]
            if (any(b[0] <= width * 400 or b[1] <= accounts[0]['locator']['rect'][3] for b in boxes)
                    or boxes[0][2] >= boxes[1][0]
                    or max(b[1] for b in boxes) >= min(b[3] for b in boxes)
                    or any(not re.fullmatch(r'[^\s/]{2}/[^\s/]{2}/(?:20)?\d{2}', t) for t in texts)):
                continue
            pairs.append((texts, boxes))
        # More than one period-like heading cannot be repaired unambiguously.
        if len(pairs) != 1:
            continue
        texts, boxes = pairs[0]
        yield values, texts, boxes


def _andrews_candidates(tables, words, width, height):
    """Only the measured full-period heading, beside one readable date."""
    candidates = {}
    for _, texts, boxes in _andrews_headings(tables, width, height):
        for side in (0, 1):
            if _date_text(texts[side]) or not _full_date(texts[1-side]):
                continue
            box = boxes[side]
            matches = [i for i, w in enumerate(words) if w[4] == texts[side]
                       and w[0]*1000 >= box[0]-1000 and w[1]*1000 >= box[1]-1000
                       and w[2]*1000 <= box[2]+1000 and w[3]*1000 <= box[3]+1000]
            if len(matches) == 1:
                candidates[matches[0]] = (side, _full_date(texts[1-side]))
    return candidates


def _candidates(tables, words):
    """Use measured cells under all three exact Merrick column headings."""
    found = set()
    def add(text, box):
        if not box or len(box) != 4 or not 3 <= len(text) <= 12 or _date_text(text):
            return
        # The table reader can trim overlapping OCR line boxes by a fraction
        # of a point. Match the same text within one point, never elsewhere on
        # the page. Multiple matches remain ambiguous.
        matches = [i for i, w in enumerate(words) if w[4] == text
                   and w[0] * 1000 >= box[0] - 1000 and w[1] * 1000 >= box[1] - 1000
                   and w[2] * 1000 <= box[2] + 1000 and w[3] * 1000 <= box[3] + 1000]
        if len(matches) == 1:
            found.add(matches[0])
    for table in tables:
        values = table.to_json().get('table', {}).get('values', [])
        rows = {}
        for cell in values:
            rows.setdefault(cell['row'], []).append(cell)
        labels = {c['text'].strip() for c in values}
        if not {'MERRICK BANK', 'Transactions, Payments and Credits'} <= labels:
            continue
        header = None
        for _, cells in sorted(rows.items()):
            cells = sorted(cells, key=lambda c: c['column'])
            texts = [c['text'].strip() for c in cells]
            for index, text in enumerate(texts):
                labelled = re.fullmatch(r'Statement Date:\s*(\S+)', text)
                if labelled:
                    add(labelled[1], cells[index]['locator'].get('rect'))
                elif text in ('Statement Date:', 'Statement Date', 'Billing Cycle Closing Date') and index + 1 < len(cells):
                    add(texts[index + 1], cells[index + 1]['locator'].get('rect'))
            if texts == ['Trans Date', 'Item Description', 'Amount']:
                header = [c['locator'].get('rect') for c in cells]
                if any(not box or len(box) != 4 for box in header):
                    header = None
                continue
            if any(t == 'Interest Charge Calculation' or re.fullmatch(r'20\d{2} Totals Year-to-Date', t) for t in texts):
                header = None
            if header is None or len(cells) < 3 or not 3 <= len(texts[0]) <= 8 or _date_text(texts[0]):
                continue
            boxes = [c['locator'].get('rect') for c in cells]
            if any(not box or len(box) != 4 for box in boxes):
                continue
            first = boxes[0]
            amount_index = len(cells) - (2 if texts[-1] == '-' else 1)
            if (abs(first[0] - header[0][0]) > 6000 or first[2] >= header[1][0]
                    or first[1] <= max(b[3] for b in header)
                    or not any(abs(b[0] - header[1][0]) <= 6000 for b in boxes[1:-1])
                    or amount_index < 2
                    or abs(boxes[amount_index][2] - header[2][2]) > 10000
                    or not re.search(r'\d', texts[amount_index])
                    or max(b[1] for b in boxes) >= min(b[3] for b in boxes)):
                continue
            add(texts[0], first)
    return sorted(found)[:80]


def _complete_calendar_date(text):
    """A full calendar date can omit a leading zero, but never its year."""
    if not re.fullmatch(r'\d{1,2}/\d{1,2}/(?:20)?\d{2}', text) or not _date_text(text):
        return None
    month, day, year = map(int, text.split('/'))
    return date(2000 + year if year < 100 else year, month, day)


def _merrick_closing_candidates(tables, words, width, height):
    """Revisit a conflicting closing date using two other printed anchors."""
    found = {}
    for table in tables:
        cells = table.to_json().get('table', {}).get('values', [])
        labels = {c['text'].strip() for c in cells}
        if not {'MERRICK BANK', 'Transactions, Payments and Credits'} <= labels:
            continue
        def box(cell):
            return cell.get('locator', {}).get('rect', [])
        headings = []
        for cell in cells:
            match = re.fullmatch(r'Statement Date:\s*(\S+)', cell['text'].strip())
            b = box(cell)
            if (match and _full_date(match[1]) and len(b) == 4
                    and b[0] > width * 600 and b[3] < height * 150):
                headings.append((cell, match[1], _full_date(match[1])))
        if len(headings) != 1:
            continue
        heading, original_date, expected = headings[0]
        years = {int(m[1]) for text in labels if (m := re.fullmatch(r'(20\d{2}) Totals Year-to-Date', text))}
        if years != {expected.year}:
            continue
        rows = {}
        for cell in cells:
            rows.setdefault(cell['row'], []).append(cell)
        targets = []
        for row in rows.values():
            row.sort(key=lambda c: c['column'])
            for index, cell in enumerate(row[:-1]):
                if cell['text'].strip() != 'Billing Cycle Closing Date':
                    continue
                value = row[index + 1]
                a, b = box(cell), box(value)
                if (len(a) != 4 or len(b) != 4 or a[2] >= b[0]
                        or max(a[1], b[1]) >= min(a[3], b[3])
                        or b[1] <= box(heading)[3] or b[3] >= height * 600):
                    continue
                targets.append(value)
        if len(targets) != 1:
            continue
        target = targets[0]
        text, b = target['text'].strip(), box(target)
        if _full_date(text) == expected or not 5 <= len(text) <= 12:
            continue
        matches = [i for i, w in enumerate(words) if w[4] == text
            and w[0]*1000 >= b[0]-1000 and w[1]*1000 >= b[1]-1000
            and w[2]*1000 <= b[2]+1000 and w[3]*1000 <= b[3]+1000]
        if len(matches) == 1:
            found[matches[0]] = dict(date=expected, original_date=original_date,
                statement_date_rect=box(heading), year_to_date_year=expected.year)
    return found


def reread_financial_dates(page, data, *, rotation, image_width, image_height,
                           reader, deadline, language):
    """Return copied OCR data and retained comparisons; no file or case writes."""
    if reader is None:
        return data, []
    page_text = ' '.join(text.strip() for text in data['text'] if text.strip())
    merrick = 'MERRICK BANK' in page_text and 'Transactions, Payments and Credits' in page_text
    andrews = 'Andrews' in page_text and 'AccountStatement' in re.sub(r'\s+', '', page_text)
    if (not merrick and not andrews) or deadline - time.monotonic() < 2:
        return data, []
    words = project_ocr_words(data, rotation=rotation, image_width=image_width,
        image_height=image_height, page_width=page.rect.width, page_height=page.rect.height)
    tables = reader.read_positioned_ocr_words(words, page_number=page.number + 1,
        page_width=page.rect.width, page_height=page.rect.height)
    periods = _andrews_candidates(tables, words, page.rect.width, page.rect.height) if andrews else {}
    closing_refs = _merrick_closing_candidates(tables, words, page.rect.width, page.rect.height) if merrick else {}
    candidates = sorted(set(_candidates(tables, words)) | set(closing_refs)) if merrick else sorted(periods)
    if not merrick:
        deadline = min(deadline, time.monotonic() + 15)
    indices = [i for i, text in enumerate(data['text']) if text.strip()]
    result, records = data, []
    for index in candidates:
        if deadline - time.monotonic() < 2:
            break
        word = words[index]
        clip = (fitz.Rect(word[:4]) + (-2, -2, 2, 2)) & page.rect
        if clip.is_empty or clip.width * clip.height * 100 > 1_000_000:
            continue
        image = None
        try:
            resolutions = (600, 450) if index in periods else (720, 600)
            pix = page.get_pixmap(matrix=fitz.Matrix(resolutions[0]/72, resolutions[0]/72), clip=clip,
                                 colorspace=fitz.csRGB, alpha=False, annots=True)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            if rotation:
                oriented = image.rotate(-rotation, expand=True, fillcolor='white')
                image.close()
                image = oriented
            observations = []
            for dpi in resolutions:
                if dpi != resolutions[0]:
                    # A complete primary line reading can be checked again at
                    # another resolution. Raw-line mode (13) may corroborate
                    # it, but cannot originate a date when mode 7 only reads
                    # fragments. Conflicting valid dates are never outvoted.
                    valid = [o['text'] for o in observations if _date_text(o['text'])]
                    if index not in closing_refs and (len(valid) != 1 or len(observations) != 2
                            or not _date_text(observations[0]['text'])):
                        break
                    image.close()
                    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), clip=clip,
                        colorspace=fitz.csRGB, alpha=False, annots=True)
                    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    if rotation:
                        oriented = image.rotate(-rotation, expand=True, fillcolor='white')
                        image.close()
                        image = oriented
                for mode in (7, 13):
                    remaining = deadline - time.monotonic()
                    if remaining < 1:
                        break
                    reading = pytesseract.image_to_string(image, lang=language,
                        config=f'--oem 1 --psm {mode} --dpi {dpi} -c tessedit_char_whitelist=0123456789/',
                        timeout=min(10, remaining)).strip()
                    observations.append(dict(dpi=dpi, segmentation_mode=mode, text=reading))
            readings = [o['text'] for o in observations if _date_text(o['text'])]
            if index in closing_refs:
                # A broken primary can be checked against the separately
                # printed full heading and YTD year, only for this duplicate
                # closing-date field. Transaction dates keep the stricter rule.
                complete = [(o, _complete_calendar_date(o['text'])) for o in observations if _complete_calendar_date(o['text'])]
                expected = closing_refs[index]['date']
                if (len(observations) != 4 or len(complete) < 2
                        or len({o['dpi'] for o, _ in complete}) != 2
                        or any(value != expected for _, value in complete)):
                    continue
                readings = [expected.strftime('%m/%d/%y')]
            elif (not observations or not _date_text(observations[0]['text'])
                    or len(readings) < 2 or len(set(readings)) != 1):
                continue
            if index in periods:
                side, other = periods[index]
                value = _full_date(readings[0])
                if value is None:
                    continue
                start, end = (value, other) if side == 0 else (other, value)
                if not 0 <= (end-start).days <= 62:
                    continue
            if result is data:
                result = deepcopy(data)
            result['text'][indices[index]] = readings[0]
            records.append(dict(method='tesseract_date_crop_consensus',
                page=page.number + 1, rect=[round(v * 1000) for v in word[:4]],
                original_text=word[4], text=readings[0], dpi=resolutions[0], segmentation_modes=[7, 13],
                character_set='0123456789/', observations=observations))
            if index in closing_refs:
                ref = closing_refs[index]
                records[-1]['agreement_with'] = dict(statement_date=ref['original_date'],
                    statement_date_rect=ref['statement_date_rect'], year_to_date_year=ref['year_to_date_year'])
        except (RuntimeError, pytesseract.TesseractError):
            # An optional retry cannot discard a completed page reading.
            continue
        finally:
            if image is not None:
                image.close()
    return result, records
