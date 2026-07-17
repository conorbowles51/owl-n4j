import pytest

from app.pipeline import merge_orchestrator
from app.pipeline.merge_relationships import aggregate_relationships_for_merge


def test_aggregate_relationships_preserves_provenance_and_strips_identity_fields() -> None:
    entities = [
        {
            "key": "source-1",
            "name": "Source One",
            "relationships": [
                {
                    "type": "OWNS",
                    "direction": "outgoing",
                    "target_key": "target-1",
                    "source_files": ["file-a.pdf"],
                    "source_quotes": ["quote a"],
                    "properties": {
                        "source_id": "source-1",
                        "target_id": "target-1",
                        "case_id": "case-1",
                        "source_files": ["file-b.pdf"],
                        "source_quotes": ["quote b"],
                        "detail": "beneficial ownership",
                        "confidence": 0.82,
                    },
                }
            ],
        },
        {
            "key": "source-2",
            "name": "Source Two",
            "relationships": [
                {
                    "type": "OWNS",
                    "direction": "outgoing",
                    "target_key": "target-1",
                    "source_files": ["file-a.pdf", "file-c.pdf"],
                    "source_quotes": ["quote a", "quote c"],
                    "properties": {
                        "source_id": "source-2",
                        "target_id": "target-1",
                        "detail": "ignored because first non-empty wins",
                    },
                },
                {
                    "type": "OWNS",
                    "direction": "incoming",
                    "target_key": "source-1",
                    "properties": {"detail": "relationship between merged sources"},
                },
            ],
        },
    ]

    aggregated, source_names = aggregate_relationships_for_merge(entities, "case-1")

    key = ("OWNS", "outgoing", "target-1")
    assert set(aggregated) == {key}
    assert source_names[key] == "Source One"
    assert aggregated[key] == {
        "case_id": "case-1",
        "source_files": ["file-a.pdf", "file-b.pdf", "file-c.pdf"],
        "source_quotes": ["quote a", "quote b", "quote c"],
        "detail": "beneficial ownership",
        "confidence": 0.82,
    }


@pytest.mark.asyncio
async def test_write_merged_entity_stamps_manual_when_any_source_manual(monkeypatch) -> None:
    captured = {}

    async def fake_execute_write(query, params):
        captured["query"] = query
        captured["params"] = params

    monkeypatch.setattr(merge_orchestrator.neo4j_client, "execute_write", fake_execute_write)

    merged = {
        "name": "Merged Person",
        "summary": "Merged summary",
        "description": "Merged description",
        "specific_type": "Witness",
        "merged_properties": {
            "source": "ingestion",
            "user_created": False,
            "merged_note": "kept",
        },
    }
    entities = [
        {
            "name": "Ingested Person",
            "properties": {"source": "ingestion", "created_by": "extractor"},
        },
        {
            "name": "Later Manual",
            "properties": {
                "source": "manual",
                "user_created": True,
                "created_by": "later@example.com",
                "created_at": "2026-07-17T12:00:00+00:00",
            },
        },
        {
            "name": "Original Manual",
            "properties": {
                "source": "manual",
                "user_created": True,
                "created_by": "original@example.com",
                "created_at": "2026-07-16T12:00:00+00:00",
            },
        },
    ]

    _, rel_count = await merge_orchestrator._write_merged_entity(
        merged,
        entities,
        "case-1",
        "job-1",
        "Person",
    )

    assert rel_count == 0
    props = captured["params"]["props"]
    assert props["user_created"] is True
    assert props["source"] == "manual"
    assert props["created_by"] == "original@example.com"
    assert props["created_at"] == "2026-07-16T12:00:00+00:00"
    assert props["merged_note"] == "kept"


def test_manual_provenance_for_merge_omits_stamp_for_ingested_sources() -> None:
    assert merge_orchestrator._manual_provenance_for_merge(
        [
            {
                "name": "Ingested",
                "properties": {
                    "source_files": ["report.pdf"],
                    "confidence": 0.9,
                },
            }
        ]
    ) == {}
