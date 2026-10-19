from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from sqlalchemy.dialects import postgresql

from app.services.evidence_table_geometry import (
    group_per_table_by_page,
    replace_evidence_table_geometry,
)


def _located_entry(page: int, values: list | None = None) -> dict:
    """A geometry-bearing ``per_table`` entry whose table sits on ``page``."""
    return {
        "table_source": "camelot-lattice",
        "geometry_source": "camelot",
        "table": {
            "page": page,
            "table": {"kind": "page_rectangle", "page": page},
            "values": values or [],
            "unlocated_values": 0,
        },
    }


def _metadata(per_table: list) -> dict:
    return {"table_geometry": {"per_table": per_table}}


def test_groups_geometry_bearing_entries_by_their_page() -> None:
    first = _located_entry(2)
    second = _located_entry(1)
    third = _located_entry(2)

    by_page, without_geometry, invalid = group_per_table_by_page(
        _metadata([first, second, third])
    )

    assert by_page == {1: [second], 2: [first, third]}
    assert without_geometry == 0
    assert invalid == 0


def test_entries_without_geometry_are_counted_not_stored() -> None:
    geometry_less = {"table_source": "camelot-lattice", "geometry_source": "none"}

    by_page, without_geometry, invalid = group_per_table_by_page(
        _metadata([geometry_less, _located_entry(1)])
    )

    assert list(by_page) == [1]
    assert without_geometry == 1
    assert invalid == 0


def test_malformed_entries_are_counted_invalid_not_raised_on() -> None:
    by_page, without_geometry, invalid = group_per_table_by_page(
        _metadata(
            [
                "not a mapping",
                {"table": {"page": 0}},
                # bool is an int subclass; a True page must not become page 1.
                {"table": {"page": True}},
                {"table": ["page missing entirely"]},
            ]
        )
    )

    assert by_page == {}
    assert without_geometry == 0
    assert invalid == 4


def test_missing_metadata_groups_nothing() -> None:
    assert group_per_table_by_page(None) == ({}, 0, 0)
    assert group_per_table_by_page({}) == ({}, 0, 0)
    assert group_per_table_by_page({"table_geometry": {}}) == ({}, 0, 0)


async def test_replace_deletes_first_then_inserts_pages_in_order() -> None:
    db = AsyncMock()
    evidence_id = uuid4()
    job_id = uuid4()
    later_page = _located_entry(3)
    earlier_page = _located_entry(1, values=[{"row": 0, "column": 0, "text": "x"}])

    result = await replace_evidence_table_geometry(
        db,
        evidence_file_id=evidence_id,
        engine_job_id=job_id,
        metadata=_metadata([later_page, earlier_page]),
    )

    statements = [call.args[0] for call in db.execute.await_args_list]
    assert len(statements) == 3

    delete_compiled = statements[0].compile(dialect=postgresql.dialect())
    assert "DELETE FROM evidence_table_geometry" in str(delete_compiled)
    assert evidence_id in delete_compiled.params.values()

    first_insert = statements[1].compile(dialect=postgresql.dialect())
    assert "INSERT INTO evidence_table_geometry" in str(first_insert)
    assert first_insert.params["evidence_file_id"] == evidence_id
    assert first_insert.params["engine_job_id"] == job_id
    assert first_insert.params["page_number"] == 1
    assert first_insert.params["payload"] == [earlier_page]

    second_insert = statements[2].compile(dialect=postgresql.dialect())
    assert second_insert.params["page_number"] == 3
    assert second_insert.params["payload"] == [later_page]

    assert db.commit.await_count == 1
    assert result.pages_written == 2
    assert result.entries_written == 2
    assert result.wrote_anything


async def test_a_run_with_no_geometry_still_clears_the_previous_run() -> None:
    db = AsyncMock()
    evidence_id = uuid4()

    result = await replace_evidence_table_geometry(
        db,
        evidence_file_id=evidence_id,
        engine_job_id=None,
        metadata=None,
    )

    statements = [call.args[0] for call in db.execute.await_args_list]
    assert len(statements) == 1
    assert "DELETE FROM evidence_table_geometry" in str(
        statements[0].compile(dialect=postgresql.dialect())
    )
    assert db.commit.await_count == 1
    assert not result.wrote_anything
    assert result.pages_written == 0
    assert result.entries_written == 0


async def test_string_identifiers_are_coerced_to_uuids() -> None:
    db = AsyncMock()
    evidence_id = uuid4()
    job_id = uuid4()

    result = await replace_evidence_table_geometry(
        db,
        evidence_file_id=str(evidence_id),
        engine_job_id=str(job_id),
        metadata=_metadata([_located_entry(1)]),
    )

    insert_compiled = db.execute.await_args_list[-1].args[0].compile(
        dialect=postgresql.dialect()
    )
    assert insert_compiled.params["evidence_file_id"] == evidence_id
    assert isinstance(insert_compiled.params["evidence_file_id"], UUID)
    assert insert_compiled.params["engine_job_id"] == job_id
    assert result.entries_without_geometry == 0
    assert result.entries_invalid == 0
