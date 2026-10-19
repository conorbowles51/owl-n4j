"""Tests for rendering an evidence page as the image a rectangle refers to.

``render_page_png`` is the last step of the locator contract: a rectangle
stored in displayed-space millipoints is drawn as fractions of a page image,
so the image must be the page as displayed, at the page's own aspect ratio,
and of exactly the page that was asked for.  The silent failures this module
exists to catch are the ones a viewer cannot see: an image of the wrong page
under a confident highlight, an aspect ratio the caller distorted, a zoom
computed against the wrong dimension, and a refusal that should have happened
but did not.

The module is tested three ways, from cheapest to dearest:

*Against fakes.*  The service is deliberately fitz-free and written against
the shape of a fitz document, so every refusal and every argument it passes
onward is checkable on any Python.  These tests pin the arithmetic (which
page is loaded, what matrix is requested, whose bytes come back) by recording
what the fakes were asked.

*Against the real library, where installed.*  PyMuPDF is not in
requirements.txt, so these are skipped rather than failed in its absence.
They pin the two facts the module docstring asserts about the library --
that a plain 6-tuple is accepted as a matrix, and that a rotated page's
pixmap shares the orientation of its displayed ``rect`` -- because both were
measured, not read, and a library release could change either.

*The endpoint, read rather than called.*  ``routers.evidence`` imports
``routers.auth``, which imports ``jose``, which is not installed in every
environment this suite runs in -- the same reason the suite already reports
one collection error, and the reason ``test_financial_route_check`` reads its
endpoint statically.  The properties pinned here are the ones no executed
test elsewhere would notice if they regressed: the parameter bounds, the sync
``def`` that keeps a CPU-bound render out of the event loop, the resolver the
route hands its stored path to, the ``finally`` that closes the document, and
the status code each distinct absence answers with.
"""

from __future__ import annotations

import ast
import struct
import unittest
from pathlib import Path

from services.financial import PageRenderError, render_page_png

try:  # The current import name, then the historic one, then skip.
    import pymupdf as _pdf

    _PYMUPDF = True
except Exception:  # pragma: no cover - environment-dependent
    try:
        import fitz as _pdf

        _PYMUPDF = True
    except Exception:
        _pdf = None
        _PYMUPDF = False


# ---------------------------------------------------------------------------
# Fakes: a document that remembers what was asked of it
# ---------------------------------------------------------------------------


class FakeRect:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class FakePixmap:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.formats_asked = []

    def tobytes(self, kind):
        self.formats_asked.append(kind)
        return self._payload


class FakePage:
    def __init__(self, width, height, payload: bytes = b"the-rendered-bytes"):
        self.rect = FakeRect(width, height)
        self.pixmap = FakePixmap(payload)
        self.matrices = []

    def get_pixmap(self, *, matrix):
        self.matrices.append(matrix)
        return self.pixmap


class FakeDocument:
    def __init__(self, pages):
        self._pages = list(pages)
        self.loaded = []

    @property
    def page_count(self):
        return len(self._pages)

    def load_page(self, index):
        self.loaded.append(index)
        return self._pages[index]


def letter_pages(count: int = 1):
    return [FakePage(612, 792) for _ in range(count)]


# ---------------------------------------------------------------------------
# Refusals, before the document is touched
# ---------------------------------------------------------------------------


class ArgumentRefusalTests(unittest.TestCase):
    """Bad arguments are refused without a page ever being loaded.

    Each refusal also asserts ``document.loaded == []``: a service that
    validated after loading would render work it then threw away, and a
    service that loaded page ``True - 1`` would be rendering page 1 for an
    argument that is a caller bug.
    """

    def refusal(self, *, page_number, width) -> str:
        document = FakeDocument(letter_pages(3))
        with self.assertRaises(PageRenderError) as caught:
            render_page_png(document, page_number=page_number, width=width)
        self.assertEqual(document.loaded, [])
        return str(caught.exception)

    def test_a_page_number_that_is_not_a_plain_integer_is_refused(self):
        for wrong in ("2", 1.5, True, None):
            with self.subTest(page_number=wrong):
                self.assertIn(
                    "page must be an integer",
                    self.refusal(page_number=wrong, width=1200),
                )

    def test_a_page_number_below_one_is_refused_as_a_base_error(self):
        # 1-based is the locator convention; 0 here is an off-by-one in the
        # caller, not the first page.
        self.assertIn("page is 1-based; got 0", self.refusal(page_number=0, width=1200))
        self.assertIn("page is 1-based; got -3", self.refusal(page_number=-3, width=1200))

    def test_a_width_that_is_not_a_plain_integer_is_refused(self):
        for wrong in ("1200", 1200.5, True, None):
            with self.subTest(width=wrong):
                self.assertIn(
                    "width must be an integer",
                    self.refusal(page_number=1, width=wrong),
                )

    def test_a_width_below_one_pixel_is_refused(self):
        self.assertIn(
            "width must be a positive number of pixels; got 0",
            self.refusal(page_number=1, width=0),
        )
        self.assertIn("got -50", self.refusal(page_number=1, width=-50))

    def test_a_page_beyond_the_document_is_refused_with_the_count(self):
        """The message carries the real count, so the reader learns the fact
        that explains the refusal rather than just that one happened."""
        document = FakeDocument(letter_pages(3))
        with self.assertRaises(PageRenderError) as caught:
            render_page_png(document, page_number=9, width=1200)
        self.assertEqual(
            str(caught.exception),
            "page 9 was requested but the document has 3 pages",
        )
        self.assertEqual(document.loaded, [])

    def test_a_one_page_document_says_page_not_pages(self):
        document = FakeDocument(letter_pages(1))
        with self.assertRaises(PageRenderError) as caught:
            render_page_png(document, page_number=2, width=1200)
        self.assertEqual(
            str(caught.exception),
            "page 2 was requested but the document has 1 page",
        )

    def test_a_page_with_no_extent_is_refused_not_divided_by(self):
        """The zoom is width / rect.width; a zero-width page is a refusal
        with the measured size in it, not a ZeroDivisionError."""
        document = FakeDocument([FakePage(0, 792)])
        with self.assertRaises(PageRenderError) as caught:
            render_page_png(document, page_number=1, width=1200)
        self.assertIn("0x792", str(caught.exception))
        self.assertIn("no extent", str(caught.exception))

    def test_a_zero_height_page_is_also_no_extent(self):
        document = FakeDocument([FakePage(612, 0)])
        with self.assertRaises(PageRenderError) as caught:
            render_page_png(document, page_number=1, width=1200)
        self.assertIn("no extent", str(caught.exception))


# ---------------------------------------------------------------------------
# The render itself, argument by argument
# ---------------------------------------------------------------------------


class RenderArithmeticTests(unittest.TestCase):
    def test_the_page_asked_for_is_the_page_loaded(self):
        """1-based in, 0-based to the library.  The off-by-one here would be
        an image of the wrong page under a confident highlight, which is the
        one failure this whole subsystem exists to prevent."""
        document = FakeDocument(letter_pages(5))
        render_page_png(document, page_number=3, width=1200)
        self.assertEqual(document.loaded, [2])

    def test_the_first_and_last_pages_are_reachable(self):
        document = FakeDocument(letter_pages(4))
        render_page_png(document, page_number=1, width=1200)
        render_page_png(document, page_number=4, width=1200)
        self.assertEqual(document.loaded, [0, 3])

    def test_the_matrix_scales_both_axes_by_the_same_zoom(self):
        """Width 1224 on a 612-point page is exactly zoom 2, so the equality
        is exact rather than approximate.  Equal x and y zoom is what keeps
        the aspect ratio the page's own; a matrix that scaled the axes
        differently would distort the one thing the locator contract
        depends on."""
        page = FakePage(612, 792)
        render_page_png(FakeDocument([page]), page_number=1, width=1224)
        self.assertEqual(page.matrices, [(2.0, 0.0, 0.0, 2.0, 0.0, 0.0)])

    def test_the_zoom_is_computed_against_width_not_height(self):
        # A landscape page: 792 wide, 612 tall.  Zoom against height would
        # be 2.0 here; against width it is 1584/792.
        page = FakePage(792, 612)
        render_page_png(FakeDocument([page]), page_number=1, width=1584)
        self.assertEqual(page.matrices, [(2.0, 0.0, 0.0, 2.0, 0.0, 0.0)])

    def test_the_bytes_returned_are_the_pixmaps_png_bytes_verbatim(self):
        page = FakePage(612, 792, payload=b"\x89PNG-stand-in")
        result = render_page_png(FakeDocument([page]), page_number=1, width=100)
        self.assertEqual(result, b"\x89PNG-stand-in")
        self.assertEqual(page.pixmap.formats_asked, ["png"])


# ---------------------------------------------------------------------------
# The real library, where it is installed
# ---------------------------------------------------------------------------


@unittest.skipUnless(_PYMUPDF, "PyMuPDF is not installed")
class RealLibraryTests(unittest.TestCase):
    """The measured facts the service is built on, pinned against the library.

    Both dimensions asserted here were measured on PyMuPDF 1.28.2 rather
    than derived: 792 * (1200/612) is 1552.94.. and the pixmap is 1553 high;
    612 * (1200/792) is 927.27.. and the rotated pixmap is 928.  What
    matters is not the rounding rule but that the proportions are the
    displayed page's, which the fractional tolerance below asserts
    directly.
    """

    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    @staticmethod
    def png_dimensions(png: bytes):
        return struct.unpack(">II", png[16:24])

    def one_page_document(self):
        document = _pdf.open()
        document.new_page(width=612, height=792)
        return document

    def test_a_us_letter_page_renders_at_the_requested_width(self):
        document = self.one_page_document()
        try:
            png = render_page_png(document, page_number=1, width=1200)
        finally:
            document.close()
        self.assertEqual(png[:8], self.PNG_SIGNATURE)
        self.assertEqual(self.png_dimensions(png), (1200, 1553))

    def test_a_rotated_page_renders_in_its_displayed_orientation(self):
        """The fact the module contains no rotation arithmetic rests on:
        after ``set_rotation(90)`` the page's ``rect`` is landscape and the
        pixmap is too, so image and displayed-space rectangle agree without
        this code doing anything."""
        document = self.one_page_document()
        try:
            page = document.load_page(0)
            page.set_rotation(90)
            self.assertEqual((page.rect.width, page.rect.height), (792.0, 612.0))
            png = render_page_png(document, page_number=1, width=1200)
        finally:
            document.close()
        width, height = self.png_dimensions(png)
        self.assertEqual((width, height), (1200, 928))
        # The proportion is the displayed page's, within a pixel of rounding.
        self.assertAlmostEqual(height / width, 612 / 792, delta=1 / 1200)

    def test_a_page_beyond_a_real_document_is_refused(self):
        document = self.one_page_document()
        try:
            with self.assertRaises(PageRenderError) as caught:
                render_page_png(document, page_number=2, width=1200)
        finally:
            document.close()
        self.assertIn("the document has 1 page", str(caught.exception))


# ---------------------------------------------------------------------------
# The endpoint, read rather than called
# ---------------------------------------------------------------------------


def evidence_source_tree() -> ast.Module:
    path = Path(__file__).resolve().parent.parent / "routers" / "evidence.py"
    return ast.parse(path.read_text(encoding="utf-8"))


def named_function(name: str):
    for node in ast.walk(evidence_source_tree()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"routers.evidence has no {name}")


class EndpointTests(unittest.TestCase):
    """See the module docstring for why these are static."""

    def endpoint(self):
        return named_function("get_evidence_page_image")

    def test_the_endpoint_exists_and_is_a_get(self):
        paths = [
            decorator.args[0].value
            for decorator in self.endpoint().decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "get"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ]
        self.assertEqual(paths, ["/{evidence_id}/page/{page_number}/image"])

    def test_the_render_runs_in_the_threadpool(self):
        """A sync ``def``: FastAPI runs it in the threadpool, and the
        CPU-bound render never blocks the event loop.  Declared ``async``,
        every concurrent page request would queue behind this one."""
        self.assertIsInstance(self.endpoint(), ast.FunctionDef)

    def test_page_and_width_are_bounded_at_the_edge(self):
        """FastAPI turns an out-of-bounds value into a 422 before the
        handler runs; the service's own refusals stay as defence in depth
        behind it.  The width ceiling is what stops one request asking for
        a wall-sized render."""
        source = ast.unparse(self.endpoint())
        self.assertIn("PathParam(ge=1)", source)
        self.assertIn("Query(1200, ge=100, le=3000)", source)

    def test_the_router_hands_over_its_own_path_resolver(self):
        """Same reason ``test_financial_route_check`` pins this for its
        endpoint: the stored path is not assumed to be a path in this
        process, and opening it directly reads the wrong layout in a
        container."""
        self.assertIn(
            "_resolve_stored_path(record.stored_path)",
            ast.unparse(self.endpoint()),
        )

    def test_the_lookup_and_its_absences_match_the_file_endpoint(self):
        """The same record can be fetched at ``/{id}/file`` and rendered at
        ``/{id}/page/{n}/image``; the two saying different things about the
        same absence would send an investigator looking for two faults."""
        source = ast.unparse(self.endpoint())
        self.assertIn("_evidence_record_for_id", source)
        self.assertIn("'Evidence not found'", source)
        self.assertIn("'File not found on disk'", source)

    def test_only_pdfs_are_rendered(self):
        source = ast.unparse(self.endpoint())
        self.assertIn("file_path.suffix.lower() != '.pdf'", source)
        self.assertIn("'File is not a PDF'", source)

    def test_a_missing_library_is_a_503_not_a_crash(self):
        """PyMuPDF is not in requirements.txt, so its absence is a
        deployment state this endpoint must answer, not an ImportError at
        module import that would take the whole router down with it."""
        endpoint_source = ast.unparse(self.endpoint())
        self.assertIn("_load_pymupdf()", endpoint_source)
        self.assertIn("status_code=503", endpoint_source)

        loader_source = ast.unparse(named_function("_load_pymupdf"))
        self.assertIn("import pymupdf", loader_source)
        self.assertIn("import fitz", loader_source)
        self.assertIn("return None", loader_source)

    def test_a_file_that_will_not_open_is_a_422(self):
        source = ast.unparse(self.endpoint())
        self.assertIn("status_code=422", source)
        self.assertIn("'The file could not be opened as a PDF'", source)

    def test_a_service_refusal_is_a_404_carrying_the_reason(self):
        """The service writes its messages to be shown to the person who
        asked, unedited; wrapping them would throw away the sentence that
        explains the refusal."""
        handlers = [
            handler
            for node in ast.walk(self.endpoint())
            if isinstance(node, ast.Try)
            for handler in node.handlers
            if isinstance(handler.type, ast.Name)
            and handler.type.id == "PageRenderError"
        ]
        self.assertEqual(len(handlers), 1)
        handler_source = ast.unparse(handlers[0])
        self.assertIn("status_code=404", handler_source)
        self.assertIn("detail=str(error)", handler_source)

    def test_the_document_is_closed_however_the_render_ends(self):
        """A leaked file handle per failed render is the kind of fault that
        appears only under load, weeks later, as 'too many open files'."""
        closing_tries = [
            node
            for node in ast.walk(self.endpoint())
            if isinstance(node, ast.Try)
            and "document.close()" in "".join(
                ast.unparse(statement) for statement in node.finalbody
            )
        ]
        self.assertEqual(len(closing_tries), 1)
        self.assertIn(
            "render_page_png",
            "".join(ast.unparse(statement) for statement in closing_tries[0].body),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
