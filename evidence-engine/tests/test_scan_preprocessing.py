"""Scan preparation measures before it changes anything, and changes only what it measured."""
from __future__ import annotations

import io

import fitz
import numpy as np
import pytest
from PIL import Image

from app.pipeline import pdf_extraction
from app.pipeline.scan_preprocessing import FAINT_RANGE, levels, measure_skew, prepare_scan_page

LINES = [f'{index:02d}/{index + 1:02d}/2025  Synthetic payment {index}   {index * 137.25:,.2f}   {9000 - index * 41.5:,.2f}'
         for index in range(1, 25)]


def _scan(*, dpi=200, skew=0.0, faint=None, pages=1):
    """PDF bytes: each page one raster image of printed lines, damaged as asked."""
    printed = fitz.open()
    scanned = fitz.open()
    try:
        for _ in range(pages):
            source = printed.new_page(width=612, height=792)
            for row, line in enumerate(LINES):
                source.insert_text((54, 90 + row * 22), line, fontsize=10)
            pixmap = source.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
            image = Image.frombytes('L', (pixmap.width, pixmap.height), pixmap.samples)
            if faint:
                image = image.point(lambda v: int(round(255 - (255 - v) * faint)))
            if skew:
                image = image.rotate(skew, resample=Image.BICUBIC, expand=False, fillcolor=255)
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            page = scanned.new_page(width=612, height=792)
            page.insert_image(page.rect, stream=buffer.getvalue())
        return scanned.tobytes()
    finally:
        printed.close()
        scanned.close()


def _prepare(data, index=0):
    document = fitz.open(stream=data, filetype='pdf')
    return document, prepare_scan_page(document[index])


def test_clean_scan_is_left_exactly_as_scanned():
    document, prepared = _prepare(_scan())
    assert prepared is None
    document.close()


def test_digital_page_is_never_prepared():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Opening balance 1,000.00', fontsize=11)
    assert prepare_scan_page(page) is None
    document.close()


@pytest.mark.parametrize('skew', [1.0, -1.0, 2.5])
def test_tilted_scan_is_measured_and_turned_back(skew):
    document, prepared = _prepare(_scan(skew=skew))
    try:
        assert prepared is not None
        record = prepared.record
        assert record['steps'] == ['deskewed']
        assert record['deskew_degrees'] == pytest.approx(-skew, abs=0.1)
        assert record['rotation_centre'] == [306.0, 396.0]
        assert not prepared.same_frame
        # Re-measuring the prepared page finds it straight.
        image = Image.open(io.BytesIO(prepared.page.get_pixmap(dpi=300, colorspace=fitz.csGRAY).tobytes('png')))
        paper, ink = levels(image)
        angle, _ = measure_skew(image, paper, ink)
        assert abs(angle) <= 0.1
    finally:
        if prepared:
            prepared.close()
        document.close()


def test_low_resolution_scan_is_resampled_in_the_same_frame():
    document, prepared = _prepare(_scan(dpi=100))
    try:
        assert prepared.record['steps'] == ['resampled']
        assert prepared.record['native_dpi'] == pytest.approx(100, abs=1)
        assert prepared.same_frame and 'deskew_degrees' not in prepared.record
        info = prepared.page.get_image_info()
        assert len(info) == 1 and info[0]['width'] == 2550 and info[0]['height'] == 3300
    finally:
        prepared.close()
        document.close()


def test_pale_print_is_stretched_and_normal_print_is_not():
    document, prepared = _prepare(_scan(faint=0.45))
    try:
        assert prepared.record['steps'] == ['contrast_stretched']
        assert prepared.record['paper_level'] - prepared.record['ink_level'] < FAINT_RANGE
        image = Image.open(io.BytesIO(prepared.page.get_pixmap(dpi=300, colorspace=fitz.csGRAY).tobytes('png')))
        paper, ink = levels(image)
        assert paper - ink >= FAINT_RANGE
    finally:
        prepared.close()
        document.close()


def test_stretch_keeps_the_order_of_every_grey_level():
    document, prepared = _prepare(_scan(faint=0.45))
    original = document[0].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
    stretched = prepared.page.get_pixmap(dpi=300, colorspace=fitz.csGRAY)
    a = np.frombuffer(original.samples, np.uint8)
    b = np.frombuffer(stretched.samples, np.uint8)
    order = np.argsort(a, kind='stable')
    assert np.all(np.diff(b[order].astype(int)) >= 0)
    prepared.close()
    document.close()


def test_prepared_page_keeps_its_page_number_and_size():
    document, prepared = _prepare(_scan(skew=1.5, pages=3), index=2)
    try:
        assert prepared.page.number == 2
        assert prepared.page.rect == document[2].rect
        assert prepared.page.parent is prepared.document
    finally:
        prepared.close()
        document.close()


def test_rotated_page_is_not_prepared():
    document = fitz.open(stream=_scan(skew=2.0), filetype='pdf')
    document[0].set_rotation(90)
    assert prepare_scan_page(document[0]) is None
    document.close()


def test_blank_scan_is_not_prepared():
    scanned = fitz.open()
    page = scanned.new_page()
    buffer = io.BytesIO()
    Image.new('L', (850, 1100), 255).save(buffer, format='PNG')
    page.insert_image(page.rect, stream=buffer.getvalue())
    assert prepare_scan_page(page) is None
    scanned.close()


def test_kill_switch_reads_every_page_as_scanned(monkeypatch):
    document = fitz.open(stream=_scan(skew=2.0), filetype='pdf')
    monkeypatch.setattr(pdf_extraction.settings, 'pdf_scan_preprocessing', False)
    assert pdf_extraction._prepare_scan(document[0]) is None
    monkeypatch.setattr(pdf_extraction.settings, 'pdf_scan_preprocessing', True)
    prepared = pdf_extraction._prepare_scan(document[0])
    assert prepared is not None and prepared.record['steps'] == ['deskewed']
    prepared.close()
    document.close()


def test_preparation_failure_reads_the_page_as_scanned(monkeypatch):
    import app.pipeline.scan_preprocessing as module

    def broken(_page):
        raise RuntimeError('synthetic failure')

    monkeypatch.setattr(module, 'prepare_scan_page', broken)
    document = fitz.open(stream=_scan(skew=2.0), filetype='pdf')
    assert pdf_extraction._prepare_scan(document[0]) is None
    document.close()


def test_original_geometry_uses_the_original_image_when_the_page_was_turned():
    document = fitz.open(stream=_scan(skew=2.0), filetype='pdf')
    page = document[0]
    prepared = prepare_scan_page(page)
    refinements = [dict(prepared.record)]
    assert pdf_extraction._crop_page_for_original_geometry(page, prepared, refinements) is page
    assert refinements[0]['used_for'] == 'not_used'
    prepared.close()
    faint = fitz.open(stream=_scan(faint=0.45), filetype='pdf')
    faint_page = faint[0]
    prepared = prepare_scan_page(faint_page)
    refinements = [dict(prepared.record)]
    assert pdf_extraction._crop_page_for_original_geometry(faint_page, prepared, refinements) is prepared.page
    assert refinements[0]['used_for'] == 'crop_rereads'
    prepared.close()
    faint.close()
    document.close()


def test_only_words_over_blank_paper_are_dropped():
    image = Image.new('RGB', (200, 40), 'white')
    image.paste((0, 0, 0), (10, 10, 40, 30))
    image.paste((120, 120, 120), (150, 10, 160, 30))
    data = dict(text=['', '61.25', '=', 'grey', '  '], conf=['-1', '90', '3', '50', '-1'],
                left=[0, 10, 80, 150, 0], top=[0, 10, 10, 10, 0], width=[200, 30, 10, 10, 1],
                height=[40, 20, 20, 20, 1], block_num=[0, 1, 1, 1, 1], par_num=[0, 1, 1, 1, 1],
                line_num=[0, 1, 1, 1, 1], word_num=[0, 1, 2, 3, 4])
    kept, dropped = pdf_extraction._drop_inkless_words(data, image)
    assert kept['text'] == ['', '61.25', 'grey', '  ']
    assert all(len(kept[k]) == 4 for k in ('left', 'top', 'width', 'height', 'conf', 'line_num'))
    assert dropped == [dict(text='=', confidence='3', box=[80, 10, 10, 20])]
    clean = dict(data, text=['', '61.25', '', 'grey', ''])
    assert pdf_extraction._drop_inkless_words(clean, image) == (clean, [])
    # Confident words are never dropped, even over blank paper.
    sure = dict(data, conf=['-1', '90', '92', '50', '-1'])
    assert pdf_extraction._drop_inkless_words(sure, image) == (sure, [])


def test_a_box_that_just_misses_its_ink_keeps_the_word():
    image = Image.new('RGB', (100, 40), 'white')
    image.paste((0, 0, 0), (50, 10, 53, 13))
    data = dict(text=[':'], conf=['30'], left=[54], top=[10], width=[1], height=[16])
    assert pdf_extraction._drop_inkless_words(data, image) == (data, [])
    far = dict(data, left=[70])
    assert pdf_extraction._drop_inkless_words(far, image)[1] == [dict(text=':', confidence='30', box=[70, 10, 1, 16])]
