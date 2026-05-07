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
