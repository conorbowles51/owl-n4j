"""Recover omitted Santander closing strips from measured source pixels.

Only a complete printed closing label and amount agreed by four bounded crops
is added. No transaction arithmetic, neighbouring balance or guessed zero is
used. Existing closing readings, including conflicting ones, are left intact.
"""
from copy import deepcopy
import re
import time

import fitz
import pytesseract
from PIL import Image, ImageOps

from app.pipeline.financial_bbva_ocr import norm
from app.pipeline.ocr_geometry import project_ocr_words

MONEY = r'\$?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'


def closing_regions(tables, width, height):
    by_table = [table.to_json().get('table', {}).get('values', []) for table in tables]
    cells = [cell for values in by_table for cell in values]
    content = norm(' '.join(c['text'] for c in cells))
    if (not re.search(r'BANCO SANTANDER MEXICO,? S\.?A\.?', content)
            or not re.search(r'CODIGO DE CLIENTE NO\.?\s*\d+', content)
            or not re.search(r'PERIODO DEL \d{2}-[A-Z]{3}-\d{4} AL \d{2}-[A-Z]{3}-\d{4}', content)):
        return []
    rows = {}
    for index, values in enumerate(by_table):
        for cell in values:
            rect = cell.get('locator', {}).get('rect', [])
            if len(rect) != 4 or rect[0] >= rect[2] or rect[1] >= rect[3]:
                return []
            rows.setdefault((index, cell['row']), []).append(cell)
    ordered = sorted(rows.values(), key=lambda row: min(c['locator']['rect'][1] for c in row))
    columns = None
    regions = []
    for row in ordered:
        labels = {norm(c['text']): c for c in row}
        if all(name in labels for name in ('DEPOSITO','RETIRO','SALDO')) and any('FECHA' in name for name in labels):
            columns = labels
        if columns is None or not any(norm(c['text']) == 'TOTAL' for c in row):
            continue
        if sum(bool(re.fullmatch(MONEY, c['text'].strip())) for c in row) != 2:
            continue
        top = max(c['locator']['rect'][3] for c in row)/1000 + .5
        below = [c for c in cells if top*1000 <= c['locator']['rect'][1] <= (top+25)*1000]
        if any('SALDO FINAL DEL PERIODO' in norm(c['text']) for c in below):
            continue
        bottom = min([top+20, height] + [c['locator']['rect'][1]/1000-1 for c in below])
        left = columns['DEPOSITO']['locator']['rect'][0]/1000-15
        right = min(width-10, max(c['locator']['rect'][2] for c in cells)/1000+2)
        if bottom-top >= 7 and 0 <= left < right <= width and right-left <= width*.45:
            regions.append([left, top, right, bottom])
    return regions[:4]


def _observation(data, rect, dpi, threshold):
    words = [(i, str(t).strip()) for i,t in enumerate(data['text']) if str(t).strip()]
    # Ignore only isolated line-border glyphs outside the complete label/value.
    while words and re.fullmatch(r"[|‘’'`]+", words[0][1]):
        words.pop(0)
    if words:
        index, word = words[0]
        words[0] = (index, re.sub(r"^[|‘’'`]+(?=SALDO$)", '', word))
    value = ' '.join(t for _,t in words)
    match = re.fullmatch(r'SALDO FINAL DEL PERIODO:\s*('+MONEY+r')', value)
    if not match or len(words) != 5:
        return None
    if (float(data['conf'][words[-1][0]]) < 70
            or min(float(data['conf'][i]) for i,_ in words[1:4]) < 50):
        return None
    def measured(items):
        indices = [i for i,_ in items]
        return [rect[0]+(min(data['left'][i] for i in indices)-15)*72/dpi,
            rect[1]+(min(data['top'][i] for i in indices)-15)*72/dpi,
            rect[0]+(max(data['left'][i]+data['width'][i] for i in indices)-15)*72/dpi,
            rect[1]+(max(data['top'][i]+data['height'][i] for i in indices)-15)*72/dpi]
    return dict(text=value, amount=match[1], dpi=dpi, threshold=threshold,
        label_rect=measured(words[:4]), amount_rect=measured(words[4:]),
        confidence=min(float(data['conf'][i]) for i,_ in words))


def read_closing_crop(page, rect, deadline, language):
    observations = []
    for dpi in (300,450):
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),clip=fitz.Rect(rect),
            colorspace=fitz.csRGB,alpha=False,annots=True)
        with Image.frombytes('RGB',(pix.width,pix.height),pix.samples) as raw:
            with raw.convert('L') as grey:
                for threshold in (None,170):
                    remaining = deadline-time.monotonic()
                    if remaining < 1:
                        return []
                    ink = grey if threshold is None else grey.point(lambda v: 255 if v >= threshold else 0)
                    try:
                        with ImageOps.expand(ink,border=15,fill=255) as padded:
                            data = pytesseract.image_to_data(padded,lang=language,
                                config=f'--oem 1 --psm 7 --dpi {dpi}',
                                output_type=pytesseract.Output.DICT,timeout=min(5,remaining))
                    finally:
                        if ink is not grey:
                            ink.close()
                    observation = _observation(data,rect,dpi,threshold)
                    if observation is None:
                        return []
                    observations.append(observation)
    return observations


def reread_santander_closing(page, data, *, rotation, image_width, image_height, reader, deadline, language):
    if rotation or reader is None or deadline-time.monotonic() < 2:
        return data, []
    content = norm(' '.join(str(t) for t in data['text']))
    if 'SANTANDER' not in content or 'TOTAL' not in content:
        return data, []
    words = project_ocr_words(data,rotation=rotation,image_width=image_width,image_height=image_height,
        page_width=page.rect.width,page_height=page.rect.height)
    tables = reader.read_positioned_ocr_words(words,page_number=page.number+1,
        page_width=page.rect.width,page_height=page.rect.height)
    result, records = data, []
    deadline = min(deadline,time.monotonic()+20)
    for rect in closing_regions(tables,page.rect.width,page.rect.height):
        if deadline-time.monotonic() < 2:
            break
        try:
            observations = read_closing_crop(page,rect,deadline,language)
        except (RuntimeError,pytesseract.TesseractError):
            continue
        if len(observations) != 4 or len({o['amount'] for o in observations}) != 1:
            continue
        chosen = observations[0]
        if result is data:
            result = deepcopy(data)
        block = max(result.get('block_num') or [0])+1
        for value,key in [('SALDO FINAL DEL PERIODO:','label_rect'),(chosen['amount'],'amount_rect')]:
            x1,y1,x2,y2 = chosen[key]
            entry = dict(text=value,left=round(x1*image_width/page.rect.width),
                top=round(y1*image_height/page.rect.height),width=max(1,round((x2-x1)*image_width/page.rect.width)),
                height=max(1,round((y2-y1)*image_height/page.rect.height)),conf=chosen['confidence'],
                level=5,page_num=1,block_num=block,par_num=1,line_num=1,word_num=1 if key=='label_rect' else 2)
            for name,values in result.items():
                values.append(entry.get(name,0))
        records.append(dict(method='tesseract_santander_closing_crop_consensus',field='closing_balance',
            page=page.number+1,rect=[round(v*1000) for v in rect],
            original_text=None,text=chosen['text'],observations=observations))
    return result, records
