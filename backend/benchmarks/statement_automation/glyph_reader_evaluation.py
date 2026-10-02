"""Measure the glyph second reader against ground truth and against Tesseract.

Two questions, both per money cell of the synthetic corpus:

1. **Accuracy.** On each recognised page as the benchmark read it, every cell
   the crop check confirmed is read by the glyph reader with that cell left out
   of the templates, and every disputed cell is read as production reads it.
   Each reading is compared with the value printed on the page image (the
   corpus ground truth).
2. **Independence.** A second reader is only worth having if it does not make
   Tesseract's mistakes. The clean corpus gives Tesseract almost none, so each
   page image is also degraded (blur, lower resolution, JPEG artefacts, faded
   ink, noise, heavy print) and both readers read every money cell again. Templates are cut, as in
   production, only from cells where the recognised text and Tesseract agree.
   Reported: how often Tesseract is wrong, how often the glyph reader gives
   the *same* wrong value (correlated error), and how often both readers agree
   on any wrong value.

Usage, from ``backend/`` with the engine interpreter::

    python -m benchmarks.statement_automation.glyph_reader_evaluation \
        RUN_DIR/engine-readings.json [--corpus DIR] [--out report.json] [--no-degraded]

``engine-readings.json`` is written by every benchmark run. Nothing is
written except the optional report. Synthetic data only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3] / 'evidence-engine'
DEGRADATIONS = ('clean', 'blur_0.7', 'blur_1.0', 'resolution_180', 'resolution_150', 'jpeg_20', 'faded',
                'noise_15', 'noise_30', 'heavy_print', 'resolution_150_jpeg_30')
THRESHOLDS = (150, 190, 220)


def _truth_cells(corpus_dir):
    """``{(filename, page index): [(x, y, align, printed text, ocr text)]}`` from the corpus builder."""
    from benchmarks.statement_automation.corpus import FONT_SIZE, build
    truth = {}
    for entry in build():
        if 'copy_of' in entry or entry['mode'] == 'digital':
            continue
        for page_index, lines in enumerate(entry['pages']):
            truth[(entry['filename'], page_index)] = [
                (cell['x'], y + FONT_SIZE, cell['align'], cell['text'], cell['ocr'])
                for y, cells in lines for cell in cells]
    return truth


def _printed(truth_cells, rect, page_reading):
    """The printed text of the corpus cell drawn at ``rect``, or ``None``."""
    x0, y0, x1, y1 = (v / 1000 for v in rect)
    found = []
    for x, baseline, align, text, ocr in truth_cells:
        edge = x1 if align == 'right' else x0
        if abs(edge - x) < 3 and y0 - 2 < baseline < y1 + 3 and (ocr if ocr is not None else text) == page_reading:
            found.append(text)
    return found[0] if len(found) == 1 else None


def _degrade(image, kind, seed):
    """A deterministic copy of a 300 dpi strip as a worse scan would print it."""
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    if kind == 'clean':
        return image.copy()
    if kind.startswith('blur_'):
        return image.filter(ImageFilter.GaussianBlur(float(kind.split('_')[1])))
    if kind.startswith('resolution_'):
        dpi = int(kind.split('_')[1])
        small = image.resize((max(1, image.width * dpi // 300), max(1, image.height * dpi // 300)), Image.BILINEAR)
        result = small.resize(image.size, Image.BILINEAR)
        small.close()
        if kind.endswith('_jpeg_30'):
            return _degrade(result, 'jpeg_30', seed)
        return result
    if kind.startswith('jpeg_'):
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=int(kind.split('_')[1]))
        buffer.seek(0)
        with Image.open(buffer) as decoded:
            return decoded.convert('L')
    if kind == 'faded':
        return image.point(lambda value: int(110 + value * (255 - 110) / 255))
    if kind.startswith('noise_'):
        rng = np.random.default_rng(seed)
        values = np.asarray(image, dtype=np.float32) + rng.normal(0, float(kind.split('_')[1]),
                                                                  (image.height, image.width))
        return Image.fromarray(np.clip(values, 0, 255).astype(np.uint8), 'L')
    if kind == 'heavy_print':
        return image.filter(ImageFilter.MinFilter(3))
    raise ValueError(kind)


def _tesseract(strips):
    """``(unanimous reading or None, [reading per threshold])`` for each strip."""
    from app.pipeline.statement_money_verification import _read_stack, _single_threaded_tesseract, money_value
    per_threshold = []
    with _single_threaded_tesseract():
        for threshold in THRESHOLDS:
            readings = []
            for start in range(0, len(strips), 40):
                readings.extend(_read_stack(strips[start:start + 40], 300, threshold, 'eng', 30))
            per_threshold.append([text for text, _ in readings])
    result = []
    for texts in zip(*per_threshold):
        values = {money_value(t) for t in texts}
        result.append((texts[0] if len(values) == 1 and None not in values else None, list(texts)))
    return result


def _same(a, b):
    from app.pipeline.statement_money_verification import money_value
    return a is not None and b is not None and re.sub(r'\s+', '', a) == re.sub(r'\s+', '', b) \
        and money_value(a) is not None


def evaluate(readings_path, corpus_dir, degraded=True, kinds=DEGRADATIONS):
    import fitz
    from app.pipeline import statement_glyph_reader as glyphs
    from app.pipeline.statement_money_verification import METHOD, _strip, money_value
    truth = _truth_cells(corpus_dir)
    readings = json.loads(Path(readings_path).read_text())['readings']
    clean = Counter()
    clean_disputed = []
    clean_wrong = []
    independence = {kind: Counter() for kind in kinds} if degraded else {}
    correlated_examples, glyph_wrong_examples = [], []
    for path, reading in sorted(readings.items()):
        filename = Path(path).name
        records = [r for location in reading.get('source_locations') or []
                   for r in location.get('ocr_refinements') or [] if r.get('method') == METHOD]
        if not records:
            continue
        with fitz.open(Path(corpus_dir) / filename) as document:
            for record in records:
                page = document[record['page'] - 1]
                cells = [c for c in record['cells'] if c['rect']]
                printed = {id(c): _printed(truth.get((filename, record['page'] - 1), []), c['rect'],
                                           c['original_text']) for c in cells}
                cells = [c for c in cells if printed[id(c)] is not None]
                strips = [_strip(page, c['rect'], glyphs.DPI, record.get('rotation') or 0) for c in cells]
                arrays = [glyphs.ink(s) for s in strips]
                confirmed = [(i, arrays[i], c['original_text']) for i, c in enumerate(cells) if c['status'] == 'confirmed']
                for i, c in enumerate(cells):
                    length = len(re.sub(r'\s+', '', c['original_text']))
                    reader = glyphs.PageGlyphs([t for t in confirmed if t[0] != i])
                    result = reader.read(arrays[i], length)
                    key = 'confirmed' if c['status'] == 'confirmed' else 'disputed'
                    clean[key + '_cells'] += 1
                    if result['text'] is None:
                        clean[key + '_abstained'] += 1
                        clean[key + '_abstained_' + result['reason']] += 1
                    elif _same(result['text'], printed[id(c)]):
                        clean[key + '_correct'] += 1
                    else:
                        clean[key + '_wrong'] += 1
                        clean_wrong.append(dict(file=filename, status=c['status'], printed=printed[id(c)],
                            glyph=result['text'], glyphs=[(g['character'], g['score'], g['runner_up'],
                            g['runner_up_score']) for g in result['glyphs']]))
                    if key == 'disputed':
                        clean_disputed.append(dict(file=filename, page_reading=c['original_text'],
                            printed=printed[id(c)], crop=c['observations'][0]['text'] if c['observations'] else None,
                            glyph=result['text'], reason=result.get('reason'),
                            glyphs=[(g['character'], g['score'], g['runner_up'], g['runner_up_score'])
                                    for g in result['glyphs']]))
                for kind in independence:
                    seed = sum(map(ord, filename)) + record['page']
                    worse = [_degrade(s, kind, seed + n) for n, s in enumerate(strips)]
                    tesseract_readings = _tesseract(worse)
                    tesseract = [unanimous for unanimous, _ in tesseract_readings]
                    worse_arrays = [glyphs.ink(s) for s in worse]
                    agreed = [(i, worse_arrays[i], c['original_text']) for i, c in enumerate(cells)
                              if _same(tesseract[i], c['original_text'])]
                    counts = independence[kind]
                    for i, c in enumerate(cells):
                        truth_text = printed[id(c)]
                        reader = glyphs.PageGlyphs([t for t in agreed if t[0] != i])
                        glyph = reader.read(worse_arrays[i], len(re.sub(r'\s+', '', c['original_text'])))['text']
                        counts['cells'] += 1
                        t_ok, g_ok = _same(tesseract[i], truth_text), _same(glyph, truth_text)
                        counts['tesseract_' + ('correct' if t_ok else 'none' if tesseract[i] is None else 'wrong')] += 1
                        counts['glyph_' + ('correct' if g_ok else 'abstained' if glyph is None else 'wrong')] += 1
                        if tesseract[i] is not None and not t_ok:
                            counts['tesseract_wrong_glyph_' + ('same_wrong' if _same(glyph, tesseract[i])
                                else 'correct' if g_ok else 'abstained' if glyph is None else 'other_wrong')] += 1
                        # Every single Tesseract reading that parses as money but is not the
                        # printed value is one Tesseract error, unanimous or not.
                        for text in tesseract_readings[i][1]:
                            if money_value(text) is not None and not _same(text, truth_text):
                                counts['tesseract_single_reading_wrong'] += 1
                                counts['tesseract_single_reading_wrong_glyph_' + (
                                    'same_wrong' if _same(glyph, text) else 'correct' if g_ok
                                    else 'abstained' if glyph is None else 'other_wrong')] += 1
                        if glyph is not None and not g_ok:
                            glyph_wrong_examples.append(dict(kind=kind, file=filename, printed=truth_text,
                                glyph=glyph, tesseract=tesseract[i], tesseract_readings=tesseract_readings[i][1]))
                        if not t_ok and _same(glyph, tesseract[i]):
                            counts['both_agree_on_wrong_value'] += 1
                            correlated_examples.append(dict(kind=kind, file=filename, printed=truth_text,
                                tesseract=tesseract[i], glyph=glyph))
                    for image in worse:
                        image.close()
                for image in strips:
                    image.close()
    return dict(clean=dict(sorted(clean.items())), disputed=clean_disputed, wrong=clean_wrong,
                degraded={k: dict(sorted(v.items())) for k, v in independence.items()},
                correlated_examples=correlated_examples, glyph_wrong_examples=glyph_wrong_examples,
                thresholds=dict(minimum_score=glyphs.MIN_SCORE, minimum_margin=glyphs.MIN_MARGIN))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('readings')
    parser.add_argument('--corpus', default=str(Path(__file__).with_name('corpus')))
    parser.add_argument('--out')
    parser.add_argument('--no-degraded', action='store_true')
    parser.add_argument('--kinds', nargs='+', choices=DEGRADATIONS, default=list(DEGRADATIONS))
    args = parser.parse_args(argv)
    if str(ENGINE) not in sys.path:
        sys.path.insert(0, str(ENGINE))
    report = evaluate(args.readings, args.corpus, degraded=not args.no_degraded, kinds=args.kinds)
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + '\n')
    print(json.dumps(dict(clean=report['clean'], wrong=report['wrong'], degraded=report['degraded'],
                          correlated_examples=report['correlated_examples'][:20],
                          glyph_wrong_examples=report['glyph_wrong_examples'][:20]), indent=1))
    for item in report['disputed']:
        print(item['file'], item['page_reading'], '->', item['glyph'], '| printed', item['printed'],
              '| crop', item['crop'], '|', item['reason'] or '')


if __name__ == '__main__':
    main()
