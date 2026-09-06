"""Table geometry in the extraction pipeline, and the text it must not disturb.

Two things are checked here that the backend's own tests cannot check, because
they are properties of the wiring rather than of the reader.

The first is that the text is unchanged.  ``result.tables`` is already chunked,
embedded and shown to readers, so adding geometry must not move a single
character of it.  That is asserted differentially, against
``_extract_native_tables_unaided`` -- the code that shipped before geometry
existed, kept in the module for exactly this reason -- rather than against a
literal, so the comparison stays honest for tables nobody thought to write down.

The second is that the backend can actually be reached.  It is a sibling package
on disk, not an installed dependency, and the failure mode of that arrangement
is silent: an import that quietly fails leaves geometry absent in a way that
looks identical to a document that simply had no tables.  So the fallback is
tested, and so is the fact that the fallback is not what is running.

This module deliberately imports only ``app.pipeline.pdf_extraction``.  Pulling
in the wider pipeline would drag in modules that cannot be imported on every
supported interpreter, and a test that cannot run proves nothing.
"""
from __future__ import annotations

import fitz
import pytest

from app.pipeline import pdf_extraction

# The same ruled table the pre-existing extraction test uses, built the same
# way, so that the byte string asserted below is the one already in the suite.
COLUMNS = [72, 250, 430]
ROWS = [72, 110, 148]
CELLS = (
    (82, 95, "Name"),
    (260, 95, "Amount"),
    (82, 133, "Alice"),
    (260, 133, "25000"),
)
EXPECTED_CHUNK = "[Page: 1]\nName | Amount\nAlice | 25000"


def _ruled_page(document: fitz.Document) -> fitz.Page:
    page = document.new_page()
    for x_position in COLUMNS:
        page.draw_line((x_position, ROWS[0]), (x_position, ROWS[-1]), width=1)
    for y_position in ROWS:
        page.draw_line((COLUMNS[0], y_position), (COLUMNS[-1], y_position), width=1)
    for x_position, y_position, value in CELLS:
        page.insert_text((x_position, y_position), value, fontsize=10)
    return page


@pytest.fixture
def ruled_document():
    document = fitz.open()
    try:
        _ruled_page(document)
        yield document
    finally:
        document.close()


@pytest.fixture
def written_pdf(tmp_path):
    path = tmp_path / "native-table.pdf"
    document = fitz.open()
    try:
        _ruled_page(document)
        document.save(path)
    finally:
        document.close()
    return path


@pytest.fixture
def part_filled_document():
    """A table with a row that has a label and no figure.

    Statements are full of these -- a subtotal line, a carried-forward line, a
    heading spanning a column that has nothing under it -- and a fully populated
    grid cannot tell whether such a row is kept or dropped, because every rule
    for deciding agrees when every cell is filled.  Found by mutation: ``any``
    and ``all`` were indistinguishable until this page existed.
    """
    document = fitz.open()
    try:
        page = document.new_page()
        rows = [72, 110, 148, 186]
        for x_position in COLUMNS:
            page.draw_line((x_position, rows[0]), (x_position, rows[-1]), width=1)
        for y_position in rows:
            page.draw_line((COLUMNS[0], y_position), (COLUMNS[-1], y_position), width=1)
        for x_position, y_position, value in (
            (82, 95, "Name"),
            (260, 95, "Amount"),
            (82, 133, "Alice"),
            (260, 133, "25000"),
            (82, 171, "Subtotal"),  # deliberately no figure beside it
        ):
            page.insert_text((x_position, y_position), value, fontsize=10)
        yield document
    finally:
        document.close()


@pytest.fixture
def without_backend(monkeypatch):
    """A deployment that cannot see the backend package at all."""
    monkeypatch.setattr(pdf_extraction, "_table_reader", None)
    monkeypatch.setattr(pdf_extraction, "_table_reader_attempted", True)
    monkeypatch.setattr(
        pdf_extraction,
        "_table_reader_failure",
        "ModuleNotFoundError: No module named 'services'",
    )


def test_the_backend_reader_is_reachable():
    """If this fails, everything else here still passes -- on the fallback.

    Which is the whole hazard: the geometry path can be entirely absent from a
    build and nothing about the extracted text will say so.
    """
    reader = pdf_extraction._load_table_reader()
    assert reader is not None, pdf_extraction._table_reader_failure
    assert hasattr(reader, "read_tables")
    assert hasattr(reader, "chunks_of")
    assert hasattr(reader, "geometry_summary")


def test_text_is_identical_to_the_pre_geometry_extraction(ruled_document):
    page = ruled_document[0]
    with_geometry, _ = pdf_extraction._extract_native_tables(page, 1)
    unaided = pdf_extraction._extract_native_tables_unaided(page, 1)
    assert with_geometry == unaided
    assert with_geometry == [EXPECTED_CHUNK]


def test_text_is_identical_when_the_backend_is_missing(ruled_document, without_backend):
    page = ruled_document[0]
    chunks, tables = pdf_extraction._extract_native_tables(page, 1)
    assert chunks == pdf_extraction._extract_native_tables_unaided(page, 1)
    assert chunks == [EXPECTED_CHUNK]
    assert tables == []


def test_a_row_with_an_empty_cell_is_kept_by_both_paths(part_filled_document):
    """A partly-filled row is text, and must survive as the text it always was.

    The trailing separator is asserted deliberately.  It is what the pre-geometry
    code produced for a row whose last cell is blank, so it is what a reader has
    already seen and what an embedding was already built from; tidying it here
    would be a silent change to shipped output dressed up as an improvement.
    """
    page = part_filled_document[0]
    expected = "[Page: 1]\nName | Amount\nAlice | 25000\nSubtotal | "

    with_geometry, tables = pdf_extraction._extract_native_tables(page, 1)
    assert with_geometry == pdf_extraction._extract_native_tables_unaided(page, 1)
    assert with_geometry == [expected]

    # The blank cell contributes no value to locate; the five that carry text do.
    geometry = tables[0].geometry
    assert geometry.located_values == 5
    assert geometry.unlocated_values == 0
    assert "Subtotal" in {cell.text for cell in geometry.cells}


def test_every_chunk_has_its_own_geometry(ruled_document):
    chunks, tables = pdf_extraction._extract_native_tables(ruled_document[0], 1)
    assert len(chunks) == len(tables)
    # Alignment as a property of the data, not of two lists staying in step.
    assert [table.chunk for table in tables] == chunks


def test_the_geometry_locates_the_values(ruled_document):
    _, tables = pdf_extraction._extract_native_tables(ruled_document[0], 1)
    geometry = tables[0].geometry
    assert geometry is not None
    assert geometry.located_values == 4
    assert geometry.unlocated_values == 0
    assert {cell.text for cell in geometry.cells} == {
        "Name",
        "Amount",
        "Alice",
        "25000",
    }


def test_a_page_without_tables_yields_nothing_either_way():
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Prose, with no ruled table anywhere on it.")
        assert pdf_extraction._extract_native_tables(page, 1) == ([], [])
    finally:
        document.close()


def test_the_page_number_reaches_the_locator(ruled_document):
    _, tables = pdf_extraction._extract_native_tables(ruled_document[0], 4)
    assert tables[0].chunk.startswith("[Page: 4]")
    assert tables[0].geometry.locator.rectangle.page_number == 4


def test_extraction_reports_what_geometry_it_recovered(written_pdf):
    result = pdf_extraction._extract_pdf_sync(str(written_pdf))
    assert result.tables == [EXPECTED_CHUNK]

    reported = result.metadata["table_geometry"]
    assert reported["available"] is True
    assert reported["coordinate_space"] == "pdf_displayed"
    assert reported["tables"] == 1
    assert reported["located_values"] == 4
    assert reported["unlocated_values"] == 0
    assert reported["by_source"]["cell_rectangles"] == 1

    # One payload per chunk, in the same order, so a consumer can pair them.
    assert len(reported["per_table"]) == len(result.tables)
    assert reported["per_table"][0]["geometry_source"] == "cell_rectangles"
    assert "degraded_reason" not in reported["per_table"][0]


def test_the_summary_agrees_with_the_payload_it_summarises(part_filled_document, tmp_path):
    """The counts must be derived from the tables, not reported alongside them.

    This is what lets ``per_table`` be dropped by whatever eventually persists
    this metadata -- it is 99.7% of the bytes -- without the summary becoming a
    number nobody can re-derive.  A summary that disagreed with its own payload
    would be worse than no summary, because it would still look authoritative.
    """
    path = tmp_path / "part-filled.pdf"
    part_filled_document.save(path)

    result = pdf_extraction._extract_pdf_sync(str(path))
    reported = result.metadata["table_geometry"]

    per_table = reported["per_table"]
    assert reported["tables"] == len(per_table)

    values = [value for payload in per_table for value in payload["table"]["values"]]
    assert values, "a summary agreeing with an empty payload would prove nothing"
    assert reported["located_values"] == sum(1 for v in values if v.get("locator"))
    assert reported["unlocated_values"] == sum(1 for v in values if not v.get("locator"))

    # Counted over the declared key set, so a source that is genuinely zero is
    # asserted as zero rather than being quietly absent from both sides.
    counted_by_source = {source: 0 for source in reported["by_source"]}
    for payload in per_table:
        counted_by_source[payload["geometry_source"]] += 1
    assert reported["by_source"] == counted_by_source

    # Everything a consumer needs to act on survives dropping the payload.
    without_payload = {k: v for k, v in reported.items() if k != "per_table"}
    assert set(without_payload) == {
        "available",
        "coordinate_space",
        "tables",
        "located_values",
        "unlocated_values",
        "by_source",
        "by_table_source",
    }


def test_extraction_says_so_when_geometry_is_unavailable(written_pdf, without_backend):
    result = pdf_extraction._extract_pdf_sync(str(written_pdf))
    # The text survives the backend being absent, which is the point.
    assert result.tables == [EXPECTED_CHUNK]

    reported = result.metadata["table_geometry"]
    assert reported["available"] is False
    assert "No module named" in reported["reason"]
    assert reported["text_only_tables"] == 1
    # No counts at all, rather than counts of zero: a build that cannot see the
    # backend must not be reportable as one that looked and found nothing.
    assert "located_values" not in reported


def test_a_reader_that_raises_costs_tables_not_the_document(written_pdf, monkeypatch):
    class Exploding:
        TABLE_COORDINATE_SPACE = pdf_extraction._load_table_reader().TABLE_COORDINATE_SPACE

        @staticmethod
        def read_tables(page, page_number):
            raise RuntimeError("find_tables is broken in this build")

        @staticmethod
        def chunks_of(tables):
            return []

        @staticmethod
        def geometry_summary(tables):
            return {"tables": 0, "located_values": 0, "unlocated_values": 0, "by_source": {}}

    monkeypatch.setattr(pdf_extraction, "_table_reader", Exploding)
    monkeypatch.setattr(pdf_extraction, "_table_reader_attempted", True)

    result = pdf_extraction._extract_pdf_sync(str(written_pdf))
    assert result.tables == []
    assert result.text  # the page's own text is untouched by a table failure
    assert result.metadata["table_geometry"]["available"] is True
    assert result.metadata["table_geometry"]["per_table"] == []
