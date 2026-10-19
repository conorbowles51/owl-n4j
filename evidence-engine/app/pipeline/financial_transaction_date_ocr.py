"""Reread damaged Andrews row dates from their original image regions."""
from copy import deepcopy
from datetime import date
import re
import time

import fitz
import pytesseract
from PIL import Image, ImageOps

from app.pipeline.financial_date_ocr import _andrews_headings, _full_date
from app.pipeline.ocr_geometry import project_ocr_words


def _month_day(text):
    if not re.fullmatch(r'\d{2}/\d{2}', text):
        return None
    month, day = map(int, text.split('/'))
    try:
        date(2000, month, day)
        return month, day
    except ValueError:
        return None


def _in_period(text, start, end):
    value = _month_day(text)
    if value is None:
        return False
    for year in range(start.year, end.year+1):
        try:
            if start <= date(year, *value) <= end:
                return True
        except ValueError:
            pass
    return False


def _candidates(tables, words, width, height):
    result = []
    used = set()
    for values, dates, _ in _andrews_headings(tables, width, height):
        start, end = map(_full_date, dates)
        if start is None or end is None or not 0 <= (end-start).days <= 62:
            continue
        rows = {}
        for cell in values:
            rows.setdefault(cell['row'], []).append(cell)
        for row in rows.values():
            row.sort(key=lambda c: c['column'])
            def box(c):
                return c.get('locator', {}).get('rect', [])
            if any(len(box(c)) != 4 for c in row):
                continue
            labels = [c for c in row if re.match(r'^(?:Recurring\s+)?(?:Withdrawal|Deposit)\b', c['text'].strip())
                      and width*80 < box(c)[0] < width*250]
            if len(labels) != 1:
                continue
            description = labels[0]
            date_cells = row[:row.index(description)]
            money = row[row.index(description)+1:]
            if (not date_cells or len(date_cells) > 3 or not money
                    or box(date_cells[0])[0] >= width*80
                    or box(date_cells[0])[1] <= height*200
                    or any(box(c)[2] >= box(description)[0] for c in date_cells)
                    or any(box(c)[0] < width*460 or box(c)[2] > width*680 for c in money)
                    or box(money[0])[0] >= width*560 or box(money[-1])[2] <= width*560
                    or max(box(c)[1] for c in row) >= min(box(c)[3] for c in row)):
                continue
            text = ' '.join(c['text'].strip() for c in date_cells)
            # A readable date in this period, or two printed dates, must not
            # be collapsed or reinterpreted by a single-date image pass.
            if not 1 <= len(text) <= 10 or _in_period(text, start, end):
                continue
            rect = [min(box(c)[0] for c in date_cells), min(box(c)[1] for c in date_cells),
                    max(box(c)[2] for c in date_cells), max(box(c)[3] for c in date_cells)]
            indices = sorted((i for i,w in enumerate(words)
                if w[0]*1000 >= rect[0]-1000 and w[1]*1000 >= rect[1]-1000
                and w[2]*1000 <= rect[2]+1000 and w[3]*1000 <= rect[3]+1000), key=lambda i: words[i][0])
            if (not indices or len(indices) > 3 or used.intersection(indices)
                    or ' '.join(words[i][4] for i in indices) != ' '.join(text.split())):
                continue
            used.update(indices)
            result.append(dict(indices=indices, rect=rect, text=text, start=start, end=end))
    return result[:20]


def reread_financial_transaction_dates(page, data, *, rotation, image_width, image_height,
                                       reader, deadline, language):
    content = ' '.join(t.strip() for t in data['text'] if t.strip())
    if (reader is None or 'Andrews' not in content
            or 'AccountStatement' not in re.sub(r'\s+', '', content) or deadline-time.monotonic() < 2):
        return data, []
    words = project_ocr_words(data,rotation=rotation,image_width=image_width,image_height=image_height,
        page_width=page.rect.width,page_height=page.rect.height)
    tables = reader.read_positioned_ocr_words(words,page_number=page.number+1,
        page_width=page.rect.width,page_height=page.rect.height)
    indices = [i for i,t in enumerate(data['text']) if t.strip()]
    deadline = min(deadline, time.monotonic()+15)
    result, records = data, []
    for candidate in _candidates(tables,words,page.rect.width,page.rect.height):
        if deadline-time.monotonic() < 2:
            break
        clip = (fitz.Rect([v/1000 for v in candidate['rect']])+(-2,-1,2,1)) & page.rect
        if clip.is_empty or clip.width*clip.height*40 > 1_000_000:
            continue
        observations = []
        try:
            for dpi in (300,450):
                if deadline-time.monotonic() < 2:
                    break
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),clip=clip,colorspace=fitz.csRGB,alpha=False,annots=True)
                with Image.frombytes('RGB',(pix.width,pix.height),pix.samples) as raw:
                    with ImageOps.expand(raw,border=10,fill='white') as image:
                        oriented = image.rotate(-rotation,expand=True,fillcolor='white') if rotation else image
                        try:
                            for mode in (7,13):
                                remaining = deadline-time.monotonic()
                                if remaining < 1:
                                    break
                                value = pytesseract.image_to_string(oriented,lang=language,
                                    config=f'--oem 1 --psm {mode} --dpi {dpi} -c tessedit_char_whitelist=0123456789/',
                                    timeout=min(5,remaining)).strip()
                                observations.append(dict(dpi=dpi,segmentation_mode=mode,text=value))
                        finally:
                            if oriented is not image:
                                oriented.close()
        except (RuntimeError,pytesseract.TesseractError):
            continue
        valid = [o['text'] for o in observations if _month_day(o['text'])]
        if (len(observations) != 4 or not _month_day(observations[0]['text'])
                or len(valid) < 2 or len(set(valid)) != 1
                or not _in_period(valid[0],candidate['start'],candidate['end'])):
            continue
        if result is data:
            result = deepcopy(data)
        raw_indices = [indices[i] for i in candidate['indices']]
        first = raw_indices[0]
        left, top = min(data['left'][i] for i in raw_indices), min(data['top'][i] for i in raw_indices)
        right = max(data['left'][i]+data['width'][i] for i in raw_indices)
        bottom = max(data['top'][i]+data['height'][i] for i in raw_indices)
        for key,value in dict(left=left,top=top,width=right-left,height=bottom-top,text=valid[0]).items():
            result[key][first] = value
        for i in raw_indices[1:]:
            result['text'][i] = ''
        records.append(dict(method='tesseract_transaction_date_crop_consensus',page=page.number+1,
            rect=candidate['rect'],original_text=candidate['text'],text=valid[0],
            original_words=[dict(text=words[i][4],rect=[round(v*1000) for v in words[i][:4]]) for i in candidate['indices']],
            period_start=candidate['start'].isoformat(),period_end=candidate['end'].isoformat(),
            dpi=300,segmentation_modes=[7,13],character_set='0123456789/',observations=observations))
    return result, records
