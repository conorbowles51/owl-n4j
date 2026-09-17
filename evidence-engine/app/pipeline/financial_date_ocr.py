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


def reread_financial_dates(page, data, *, rotation, image_width, image_height,
                           reader, deadline, language):
    """Return copied OCR data and retained comparisons; no file or case writes."""
    if reader is None:
        return data, []
    page_text = ' '.join(text.strip() for text in data['text'] if text.strip())
    if ('MERRICK BANK' not in page_text or 'Transactions, Payments and Credits' not in page_text
            or deadline - time.monotonic() < 2):
        return data, []
    words = project_ocr_words(data, rotation=rotation, image_width=image_width,
        image_height=image_height, page_width=page.rect.width, page_height=page.rect.height)
    tables = reader.read_positioned_ocr_words(words, page_number=page.number + 1,
        page_width=page.rect.width, page_height=page.rect.height)
    indices = [i for i, text in enumerate(data['text']) if text.strip()]
    result, records = data, []
    for index in _candidates(tables, words):
        if deadline - time.monotonic() < 2:
            break
        word = words[index]
        clip = (fitz.Rect(word[:4]) + (-2, -2, 2, 2)) & page.rect
        if clip.is_empty or clip.width * clip.height * 100 > 1_000_000:
            continue
        image = None
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(10, 10), clip=clip,
                                 colorspace=fitz.csRGB, alpha=False, annots=True)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            if rotation:
                oriented = image.rotate(-rotation, expand=True, fillcolor='white')
                image.close()
                image = oriented
            observations = []
            for dpi in (720, 600):
                if dpi == 600:
                    # A complete primary line reading can be checked again at
                    # another resolution. Raw-line mode (13) may corroborate
                    # it, but cannot originate a date when mode 7 only reads
                    # fragments. Conflicting valid dates are never outvoted.
                    valid = [o['text'] for o in observations if _date_text(o['text'])]
                    if (len(valid) != 1 or len(observations) != 2
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
            if (not observations or not _date_text(observations[0]['text'])
                    or len(readings) < 2 or len(set(readings)) != 1):
                continue
            if result is data:
                result = deepcopy(data)
            result['text'][indices[index]] = readings[0]
            records.append(dict(method='tesseract_date_crop_consensus',
                page=page.number + 1, rect=[round(v * 1000) for v in word[:4]],
                original_text=word[4], text=readings[0], dpi=720, segmentation_modes=[7, 13],
                character_set='0123456789/', observations=observations))
        except (RuntimeError, pytesseract.TesseractError):
            # An optional retry cannot discard a completed page reading.
            continue
        finally:
            if image is not None:
                image.close()
    return result, records
