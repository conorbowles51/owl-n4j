"""Evidence reads that await nothing are plain functions, so FastAPI runs them in its thread pool. As async
functions they ran on the worker's event loop: listing d5b330d1's statement files (12-20 s) held every other
request of that worker until it finished."""
import inspect

from routers import evidence


def test_the_listing_and_lookup_reads_run_in_the_thread_pool():
    for name in ('list_evidence', 'text_search', 'get_evidence_record', 'document_text_matches'):
        assert not inspect.iscoroutinefunction(getattr(evidence, name)), name


def test_files_with_the_same_time_keep_one_order():
    """Files added in one batch share created_at; ordered by it alone, d5b330d1's 3,158 files came back in a
    different order from one listing to the next (same rows)."""
    import uuid
    from services.evidence_db_storage import EvidenceDBStorage
    seen = []

    class Db:
        def scalars(self, query):
            seen.append(query)
            return type('R', (), dict(all=lambda self: []))()
    EvidenceDBStorage.list_files(Db(), case_id=uuid.uuid4())
    order = str(seen[0]).split('ORDER BY', 1)[1]
    assert 'created_at DESC' in order and 'evidence_files.id' in order
