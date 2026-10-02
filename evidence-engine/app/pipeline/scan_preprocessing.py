"""Straighten and clarify a scanned page before it is read.

Why this exists
---------------
A production scan is often tilted, coarse or pale. Tesseract reads a page in
lines: a page turned by one or two degrees puts the left and right ends of one
printed row on different text lines, so rows split, merge or vanish and the
statement is not recognised at all. A 100 or 150 dpi scan gives the money
cells too few pixels per glyph. Pale toner leaves ink lighter than the fixed
thresholds that the money-cell crop check (``statement_money_verification``)
binarises at, so a correctly read amount cannot be confirmed and the period is
held for a person.

What this does
--------------
For a page that is one full-page raster image and nothing more, three
measurements are taken, and only what they show is done:

* **resolution**: the scan's own pixels per inch. Below ``LOW_DPI`` the page
  is rendered at its native resolution and resampled to ``WORK_DPI`` with a
  Lanczos filter (measured on the v4 corpus: 100 dpi pages gave every printed
  amount after resampling; MuPDF's own upscaling lost up to 2 of 5);
* **contrast**: paper is the median grey; ink is the 5th percentile of the
  pixels at least ``INK_STEP`` levels darker than paper, after a 3x3 box blur
  (so isolated noise pixels do not count). Ink is measured among inked pixels
  only because a sparse page has too little ink for any whole-page
  percentile to land in it. When paper and ink are closer than
  ``FAINT_RANGE`` grey levels the page is stretched linearly so ink becomes
  black and paper white. 130 levels on white paper means the ink is lighter
  than grey 125, so the crop check's darkest threshold (150) keeps only the
  cores of the strokes. Measured on the v4 corpus: pale scans sit at 88 to
  107 levels, normal ones (including 100 dpi and JPEG-damaged) at 167 or
  more. A page with fewer than ``MIN_INK_PIXELS`` inked pixels is not
  measured and not stretched. A linear stretch keeps the order of
  every grey level: it adds no shape that was not printed;
* **skew**: the angle, within ``MAX_SKEW`` degrees, at which the rows of ink
  are sharpest (largest summed squared change of the horizontal ink profile).
  A page is turned only when that angle is at least ``MIN_SKEW`` degrees, is
  not at the edge of the search, and sharpens the rows by at least
  ``MIN_SKEW_GAIN`` over the page as scanned.

Nothing measured means nothing changes: ``prepare_scan_page`` returns ``None``
and the page is read exactly as before. The clean 200 dpi scans in the
benchmark corpus are left alone for that reason.

What the reader is given
------------------------
The prepared image is placed, full page, on a page of the same size in a
separate in-memory document, at the same page index, so the page reading, the
quality and crop rereads and the glyph second reader all measure the same
image and every check they apply still applies. The prepared page is used for
the image only; the original document is never modified.

Where a page was turned, the rectangles measured on it are in the straightened
frame: a printed line is horizontal there, which is what the table reader and
the backend's geometric proofs (adjacent lines, nothing read between them)
assume. The page's refinement record states the angle and the centre of the
turn, so a viewer can place a highlight on the page as displayed by turning
the rectangle back by ``-deskew_degrees`` about ``rotation_centre``.
"""
from __future__ import annotations

import io

import fitz
import numpy as np
from PIL import Image, ImageFilter

METHOD = 'scan_preprocessing'
WORK_DPI = 300
LOW_DPI = 200
FAINT_RANGE = 130
INK_STEP = 30
MIN_INK_PIXELS = 500
MAX_SKEW = 5.0
MIN_SKEW = 0.2
MIN_SKEW_GAIN = 1.05
SKEW_DPI = 100
MIN_SKEW_INK = 2000
FULL_PAGE_COVERAGE = 0.95


class PreparedScan:
    """The prepared page, its owning document and what was done to it."""

    def __init__(self, document, page, record):
        self.document = document
        self.page = page
        self.record = record

    @property
    def same_frame(self):
        """Whether rectangles on the prepared page are the original page's rectangles."""
        return not self.record.get('deskew_degrees')

    def close(self):
        self.document.close()


def _scan_image_dpi(page):
    """Native resolution of a page that is one full-page image, else ``None``."""
    if page.rotation:
        return None
    infos = [i for i in page.get_image_info() if i.get('width') and i.get('height')]
    if len(infos) != 1:
        return None
    info = infos[0]
    bbox = fitz.Rect(info['bbox']) & page.rect
    if bbox.is_empty or bbox.get_area() < FULL_PAGE_COVERAGE * page.rect.get_area():
        return None
    dpi_x = info['width'] / (bbox.width / 72)
    dpi_y = info['height'] / (bbox.height / 72)
    return min(dpi_x, dpi_y)


def _render(page, dpi):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False, annots=True)
    return Image.frombytes('L', (pix.width, pix.height), pix.samples)


def levels(image):
    """``(paper, ink)`` grey levels of a greyscale page image; ink is ``None`` when unmeasured."""
    paper = float(np.median(np.asarray(image)))
    blurred = np.asarray(image.filter(ImageFilter.BoxBlur(1)))
    inked = blurred[blurred < paper - INK_STEP]
    if inked.size < MIN_INK_PIXELS:
        return paper, None
    return paper, float(np.percentile(inked, 5))


def _stretch(image, paper, ink):
    scale = 255.0 / (paper - ink)
    lut = [int(min(255, max(0, round((value - ink) * scale)))) for value in range(256)]
    return image.point(lut)


def _row_sharpness(binary_image, angle):
    turned = binary_image.rotate(angle, resample=Image.NEAREST, fillcolor=0)
    profile = np.asarray(turned, dtype=np.float64).sum(axis=1)
    return float(np.sum(np.diff(profile) ** 2))


def measure_skew(image, paper, ink):
    """``(angle, gain)``: the turn that best straightens the rows, or ``(0.0, 1.0)``.

    ``image`` is a greyscale page; the angle is in degrees, counter-clockwise,
    as PIL's ``rotate`` takes it.
    """
    small = image.resize((max(1, round(image.width * SKEW_DPI / WORK_DPI)),
                          max(1, round(image.height * SKEW_DPI / WORK_DPI))), Image.BILINEAR)
    threshold = (paper + ink) / 2
    binary = small.point(lambda value: 255 if value < threshold else 0)
    if np.count_nonzero(np.asarray(binary)) < MIN_SKEW_INK:
        return 0.0, 1.0
    flat = _row_sharpness(binary, 0.0)
    if flat <= 0:
        return 0.0, 1.0
    coarse = [round(-MAX_SKEW + 0.25 * i, 2) for i in range(int(2 * MAX_SKEW / 0.25) + 1)]
    scores = {angle: _row_sharpness(binary, angle) for angle in coarse}
    best = max(coarse, key=lambda angle: (scores[angle], -abs(angle)))
    fine = [round(best + 0.05 * i, 2) for i in range(-5, 6) if abs(best + 0.05 * i) <= MAX_SKEW]
    for angle in fine:
        scores.setdefault(angle, _row_sharpness(binary, angle))
    best = max(fine, key=lambda angle: (scores[angle], -abs(angle)))
    return best, scores[best] / flat


def prepare_scan_page(page):
    """A :class:`PreparedScan` when the page is a scan that needs it, else ``None``."""
    native_dpi = _scan_image_dpi(page)
    if native_dpi is None:
        return None
    steps = []
    if native_dpi < LOW_DPI - 1:
        native = _render(page, max(36, round(native_dpi)))
        size = (round(page.rect.width * WORK_DPI / 72), round(page.rect.height * WORK_DPI / 72))
        image = native.resize(size, Image.LANCZOS)
        native.close()
        steps.append('resampled')
    else:
        image = _render(page, WORK_DPI)
    paper, ink = levels(image)
    record = dict(field=METHOD, native_dpi=round(native_dpi, 1), work_dpi=WORK_DPI,
                  paper_level=round(paper, 1), ink_level=None if ink is None else round(ink, 1))
    if ink is None:
        image.close()
        return None
    if paper - ink < FAINT_RANGE:
        stretched = _stretch(image, paper, ink)
        image.close()
        image = stretched
        steps.append('contrast_stretched')
        paper, ink = 255.0, 0.0
    angle, gain = measure_skew(image, paper, ink)
    record.update(measured_skew_degrees=angle, skew_gain=round(gain, 3))
    if abs(angle) >= MIN_SKEW and abs(angle) < MAX_SKEW and gain >= MIN_SKEW_GAIN:
        turned = image.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=int(round(paper)))
        image.close()
        image = turned
        steps.append('deskewed')
        record.update(deskew_degrees=angle,
                      rotation_centre=[round(page.rect.width / 2, 3), round(page.rect.height / 2, 3)])
    if not steps:
        image.close()
        return None
    record['steps'] = steps
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    image.close()
    document = fitz.open()
    try:
        for _ in range(page.number):
            document.new_page(width=page.rect.width, height=page.rect.height)
        prepared = document.new_page(width=page.rect.width, height=page.rect.height)
        prepared.insert_image(prepared.rect, stream=buffer.getvalue())
    except Exception:
        document.close()
        raise
    return PreparedScan(document, prepared, record)
