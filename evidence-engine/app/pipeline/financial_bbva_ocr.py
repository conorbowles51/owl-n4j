"""Reread damaged BBVA headings and dates from their own printed pixels.

No amounts, account identifiers or dates are inferred from other entries.
Conflicting crop readings keep the original OCR and remain for review.
"""
from copy import deepcopy
from datetime import date
import re
import time
import unicodedata

import fitz
import pytesseract
from PIL import Image, ImageOps

from app.pipeline.ocr_geometry import project_ocr_words


MONTHS = {name: i for i, name in enumerate(
    ('ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'), 1)}
CONTROLS = {'SALDO DE OPERACION INICIAL', 'SALDO DE OPERACION FINAL',
            'SALDO DE LIQUIDACION INICIAL', 'DEPOSITOS / ABONOS (+)'}


def norm(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.upper())
                           if not unicodedata.combining(c)).split())


def valid_date(value):
    match = re.fullmatch(r'(\d{2})/([A-Z]{3})', norm(value))
    if not match or match[2] not in MONTHS:
        return False
    try:
        date(2000, MONTHS[match[2]], int(match[1]))
        return True
    except ValueError:
        return False


def valid_page(value):
    match = re.fullmatch(r'PAGINA\s+(\d+)\s*/\s*(\d+)', norm(value))
    return bool(match and 1 <= int(match[1]) <= int(match[2]) <= 500)


def candidates(tables, words, width, height):
    cells = [c for table in tables for c in table.to_json().get('table', {}).get('values', [])]
    def box(c):
        return c.get('locator', {}).get('rect', [])
    cells = [c for c in cells if len(box(c)) == 4]
    products = [c for c in cells if norm(c['text']).startswith('CASH MANAGEMENT ')
                and box(c)[0] > width * 500 and box(c)[3] < height * 100]
    if len(products) != 1 or not any(re.search(r'BBVA (?:MEXICO|BANCOMER),? S\.?A\.?', norm(c['text'])) for c in cells):
        return []
    product_box = box(products[0])
    headings = [c for c in cells if norm(c['text']) == 'COD. DESCRIPCION']
    date_headers = [c for c in cells if norm(c['text']) in ('OPER', 'OPER LIQ')]
    results = []
    for cell in cells:
        rect, value = box(cell), norm(cell['text'])
        kind = None
        if (rect[0] >= product_box[0] and rect[1] >= product_box[3] - 1000
                and rect[3] <= product_box[3] + 17000 and not valid_page(value)):
            kind = 'page_number'
        elif (rect[0] > width * 480 and rect[3] < height * 600
                and value not in CONTROLS and (value.startswith('SALDO DE ') or '/ ABONOS (+)' in value)):
            kind = 'control_label'
        if kind:
            indices = [i for i, w in enumerate(words) if w[0]*1000 >= rect[0]-1000
                       and w[1]*1000 >= rect[1]-1000 and w[2]*1000 <= rect[2]+1000
                       and w[3]*1000 <= rect[3]+1000]
            if indices and ' '.join(words[i][4] for i in indices) == cell['text'].strip():
                results.append(dict(kind=kind, rect=rect, indices=indices, text=cell['text']))
    # Only tokens underneath explicit transaction-date headings and left of
    # the description column. A reference containing a slash is not a date.
    for i, word in enumerate(words):
        value = norm(word[4])
        if not re.fullmatch(r'[^\s/]{1,4}/(?:' + '|'.join(MONTHS) + ')', value) or valid_date(value):
            continue
        rect = [round(v*1000) for v in word[:4]]
        if any(rect[0] < box(h)[0] - 1000 and rect[1] > box(h)[3]
               and any(abs(box(d)[1] - box(h)[1]) < 5000 for d in date_headers) for h in headings):
            results.append(dict(kind='transaction_date', rect=rect, indices=[i], text=word[4]))
    return results[:40]


def reread_bbva_fields(page, data, *, rotation, image_width, image_height, reader, deadline, language):
    content = norm(' '.join(t for t in data['text'] if t.strip()))
    if (reader is None or 'CASH MANAGEMENT ' not in content or 'BBVA' not in content
            or deadline - time.monotonic() < 2):
        return data, []
    words = project_ocr_words(data, rotation=rotation, image_width=image_width, image_height=image_height,
                              page_width=page.rect.width, page_height=page.rect.height)
    tables = reader.read_positioned_ocr_words(words, page_number=page.number+1,
                page_width=page.rect.width, page_height=page.rect.height)
    raw_indices = [i for i, value in enumerate(data['text']) if value.strip()]
    result, records = data, []
    deadline = min(deadline, time.monotonic()+35)
    for item in candidates(tables, words, page.rect.width, page.rect.height):
        if deadline - time.monotonic() < 2:
            break
        clip = (fitz.Rect([v/1000 for v in item['rect']])+(-2,-1,2,1)) & page.rect
        if clip.is_empty or clip.width*clip.height*40 > 1_000_000:
            continue
        observations = []
        try:
            for dpi in (300, 450):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72), clip=clip,
                                     colorspace=fitz.csRGB, alpha=False, annots=True)
                with Image.frombytes('RGB',(pix.width,pix.height),pix.samples) as raw:
                    with ImageOps.expand(raw,border=10,fill='white') as padded:
                        oriented = padded.rotate(-rotation,expand=True,fillcolor='white') if rotation else padded
                        try:
                            for mode in (7, 13):
                                remaining = deadline-time.monotonic()
                                if remaining < 1:
                                    break
                                value = pytesseract.image_to_string(oriented,lang=language,
                                    config=f'--oem 1 --psm {mode} --dpi {dpi}', timeout=min(5,remaining)).strip()
                                observations.append(dict(dpi=dpi,segmentation_mode=mode,text=value))
                        finally:
                            if oriented is not padded:
                                oriented.close()
        except (RuntimeError, pytesseract.TesseractError):
            continue
        validate = {'page_number': valid_page, 'transaction_date': valid_date,
                    'control_label': lambda v: norm(v) in CONTROLS}[item['kind']]
        readings = [norm(o['text']) for o in observations if validate(o['text'])]
        if len(observations) != 4 or len(readings) < 2 or len(set(readings)) != 1:
            continue
        if result is data:
            result = deepcopy(data)
        indices = [raw_indices[i] for i in item['indices']]
        first = indices[0]
        left, top = min(data['left'][i] for i in indices), min(data['top'][i] for i in indices)
        right = max(data['left'][i]+data['width'][i] for i in indices)
        bottom = max(data['top'][i]+data['height'][i] for i in indices)
        for key, value in dict(text=readings[0],left=left,top=top,width=right-left,height=bottom-top).items():
            result[key][first] = value
        for i in indices[1:]:
            result['text'][i] = ''
        records.append(dict(method='tesseract_bbva_crop_consensus',field=item['kind'],page=page.number+1,
            rect=item['rect'],original_text=item['text'],text=readings[0],observations=observations,
            original_words=[dict(text=words[i][4],rect=[round(v*1000) for v in words[i][:4]]) for i in item['indices']]))
    return result, records
