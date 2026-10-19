"""Rendering one page of a PDF as the image a stored rectangle refers to.

A ``page_rectangle`` locator promises that its rectangle sits on the page *as
displayed*: ``capture`` stores the displayed page dimensions, which are what
PyMuPDF's ``page.rect`` reports after rotation is applied.  A pixmap rendered
from the same page shares that orientation -- measured on PyMuPDF 1.28.2, a
US-Letter page at rotation 90 reports a 792x612 ``rect`` and renders a pixmap
of the same aspect.  So an image produced here and a rectangle normalised to
fractions of its stored ``page_size`` agree by construction, and this module
contains no rotation arithmetic because the library has already applied the
rotation on both sides of the agreement.

The module is deliberately free of PyMuPDF, in the same way and for the same
reason as ``pdf_tables``: it is written against the shape of a fitz document
(``page_count``, ``load_page``, a page's ``rect`` and ``get_pixmap``), so the
logic is testable on any Python whether or not the library is installed, and
the caller that owns a real document passes it in behind its own guarded
import.  ``get_pixmap`` accepts a plain 6-tuple as its matrix (verified on
1.28.2), which is what keeps the zoom computation here instead of behind a
``fitz.Matrix`` this module would otherwise have to import.

The caller chooses only the width of the image.  Height follows from the
page's own aspect ratio, because a viewer drawing highlights as fractions of
the page must be given an image whose proportions are the page's; letting a
caller pick both dimensions would let it distort the one thing the locator
contract depends on.

Refusals raise :class:`PageRenderError` with a message written to be shown to
the person who asked, unedited.  That matches the locator reader's contract on
the frontend: when a page cannot be rendered faithfully, the honest failure is
a sentence, not a wrong image.
"""
from __future__ import annotations


class PageRenderError(Exception):
    """A page that cannot be rendered, said plainly.

    The message is written to be shown to the person who asked for the page.
    """


def _is_plain_integer(value: object) -> bool:
    """True for an int and false for everything else, including bool.

    ``bool`` is an ``int`` subclass, and a page number of ``True`` is a bug in
    the caller, not page 1.  The same check guards locator fields for the same
    reason.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def render_page_png(document, *, page_number: int, width: int) -> bytes:
    """Render one page of ``document`` as a PNG ``width`` pixels wide.

    ``document`` is fitz-``Document``-shaped: ``page_count`` and 0-based
    ``load_page``, with pages carrying ``rect`` and ``get_pixmap``.
    ``page_number`` is 1-based, as locators store it.

    Raises :class:`PageRenderError` for a page that does not exist, a page
    with no extent, or arguments of the wrong shape.  Never returns an image
    for a page other than the one asked for.
    """
    if not _is_plain_integer(page_number):
        raise PageRenderError(f"page must be an integer, got {page_number!r}")
    if page_number < 1:
        raise PageRenderError(f"page is 1-based; got {page_number}")
    if not _is_plain_integer(width):
        raise PageRenderError(f"width must be an integer, got {width!r}")
    if width < 1:
        raise PageRenderError(f"width must be a positive number of pixels; got {width}")

    count = document.page_count
    if page_number > count:
        pages = "page" if count == 1 else "pages"
        raise PageRenderError(
            f"page {page_number} was requested but the document has {count} {pages}"
        )

    page = document.load_page(page_number - 1)
    rect = page.rect
    if rect.width <= 0 or rect.height <= 0:
        raise PageRenderError(
            f"page {page_number} reports a size of {rect.width}x{rect.height} points; "
            "a page with no extent cannot be rendered"
        )

    zoom = width / rect.width
    pixmap = page.get_pixmap(matrix=(zoom, 0.0, 0.0, zoom, 0.0, 0.0))
    return pixmap.tobytes("png")
