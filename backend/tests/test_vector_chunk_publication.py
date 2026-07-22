from services.vector_db_service import VectorDBService


class FakeChunkCollection:
    def __init__(self) -> None:
        self.requested_results: int | None = None

    def count(self) -> int:
        return 4

    def query(self, *, query_embeddings, n_results, where):  # noqa: ANN001
        self.requested_results = n_results
        rows = [
            ("draft", "unfinished", {"ingestion_state": "draft"}, 0.01),
            ("old", "retired", {"ingestion_state": "inactive"}, 0.02),
            ("current", "published", {"ingestion_state": "active"}, 0.03),
            ("legacy", "pre-publication data", {}, 0.04),
        ][:n_results]
        return {
            "ids": [[row[0] for row in rows]],
            "documents": [[row[1] for row in rows]],
            "metadatas": [[row[2] for row in rows]],
            "distances": [[row[3] for row in rows]],
        }


class FakeDeletionCollection:
    def __init__(self) -> None:
        self.queries: list[dict] = []
        self.deleted_ids: list[str] = []

    def get(self, *, where):  # noqa: ANN001
        self.queries.append(where)
        selector = where["$and"][1]
        field, value = next(iter(selector.items()))
        matches = {
            ("evidence_file_id", "evidence-1"): ["new-1", "new-2"],
            ("doc_id", "evidence-1"): ["new-1"],
            ("doc_key", "reportpdf"): ["legacy-key"],
            ("doc_id", "reportpdf"): ["legacy-key"],
            ("doc_id", "Report.pdf"): ["legacy-name"],
            ("file_name", "Report.pdf"): ["new-2", "legacy-name"],
        }
        return {"ids": matches.get((field, value), [])}

    def delete(self, *, ids):  # noqa: ANN001
        self.deleted_ids.extend(ids)


def test_chunk_search_hides_draft_and_retired_revisions() -> None:
    collection = FakeChunkCollection()
    service = VectorDBService.__new__(VectorDBService)
    service._chunks_healthy = True
    service.chunk_collection = collection
    service._check_dimension = lambda *_args: True

    results = service.search_chunks([0.1, 0.2], top_k=2, filter_metadata={"case_id": "case-1"})

    assert [result["id"] for result in results] == ["current", "legacy"]
    assert collection.requested_results == 4


def test_document_chunk_deletion_covers_stable_and_legacy_identities() -> None:
    collection = FakeDeletionCollection()
    service = VectorDBService.__new__(VectorDBService)
    service.chunk_collection = collection

    deleted = service.delete_chunks_for_document(
        case_id="case-1",
        evidence_file_id="evidence-1",
        doc_key="reportpdf",
        file_name="Report.pdf",
    )

    assert deleted == 4
    assert set(collection.deleted_ids) == {"new-1", "new-2", "legacy-key", "legacy-name"}
    assert all(query["$and"][0] == {"case_id": "case-1"} for query in collection.queries)


def test_chunk_search_stops_when_filtered_case_results_are_exhausted() -> None:
    class SparseCaseCollection:
        def __init__(self) -> None:
            self.calls = 0

        def count(self) -> int:
            return 10_000

        def query(self, **_kwargs):
            self.calls += 1
            return {
                "ids": [["draft", "active", "inactive"]],
                "documents": [["draft", "published", "retired"]],
                "metadatas": [[
                    {"ingestion_state": "draft"},
                    {"ingestion_state": "active"},
                    {"ingestion_state": "inactive"},
                ]],
                "distances": [[0.01, 0.02, 0.03]],
            }

    collection = SparseCaseCollection()
    service = VectorDBService.__new__(VectorDBService)
    service._chunks_healthy = True
    service.chunk_collection = collection
    service._check_dimension = lambda *_args: True

    results = service.search_chunks(
        [0.1, 0.2],
        top_k=2,
        filter_metadata={"case_id": "small-case"},
    )

    assert [result["id"] for result in results] == ["active"]
    assert collection.calls == 1
