"""Reread damaged money cells on measured Andrews statement payment rows.

Amounts come from the source image, never from balancing arithmetic. Complete
matching visual readings are required; conflicting signs or digits stay flagged.
"""
from copy import deepcopy
import re
import time

import fitz
import pytesseract
from PIL import Image

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
            if len(row) != 4:
                continue
            date_cell, description, amount, balance = row
            verb = re.match(r'^(?:Recurring\s+)?(Withdrawal|Deposit)\b', description['text'].strip())
            if (not verb or not re.fullmatch(r'\S{4,7}(?: \d{2}/\d{2})?', date_cell['text'].strip())
                    or box(date_cell)[0] >= width*.08 or box(date_cell)[1] <= height*.2
                    or not width*.08 < box(description)[0] < width*.25
                    or box(description)[2] >= box(amount)[0]
                    or not width*.46 <= box(amount)[0] < box(amount)[2] < box(balance)[0]
                    or box(balance)[2] > width*.68
                    or max(box(c)[1] for c in row) >= min(box(c)[3] for c in row)):
                continue
            for field, cell in [('amount', amount), ('balance', balance)]:
                text = cell['text'].strip()
                b = box(cell)
                if _money(re.sub(r'\s+', '', text)) or len(text) > 24 or b[2]-b[0] > width*.13:
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
                    verb=verb[1], adjustment='Adjustment' in description['text']))
    return candidates[:40]


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
            if (not observations or not _money(observations[0]['text'])
                    or len(valid) < 2 or len(set(valid)) != 1):
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
                original_words=[dict(text=w[4],rect=[round(v*1000) for v in w[:4]]) for w in original_words],
                dpi=720,segmentation_modes=[7,13],character_set='0123456789.,-+',observations=observations))
        except (RuntimeError,pytesseract.TesseractError):
            continue
    return result, records
