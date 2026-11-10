"""Each file of a batch shows the entities and relationships its own text supports, not the batch's totals."""

import inspect
from types import SimpleNamespace

from app.pipeline import batch_orchestrator
from app.pipeline.batch_orchestrator import file_counts
from scripts.recount_batch_relationships import planned_changes


def _item(*files):
    return SimpleNamespace(source_files=list(files))


def test_relationships_counted_per_file():
    entities = [_item("a.dotx"), _item("a.dotx", "b.dotx"), _item("b.dotx")]
    relationships = [_item("a.dotx")] * 10 + [_item("b.dotx")] * 13
    assert file_counts("a.dotx", entities, relationships) == (2, 10)
    assert file_counts("b.dotx", entities, relationships) == (2, 13)
    assert file_counts("plan.pdf", entities, relationships) == (0, 0)


def test_batch_pipeline_never_writes_batch_total_to_a_file():
    source = inspect.getsource(batch_orchestrator.run_batch_pipeline)
    assert "relationship_count=len(resolved_rels)" not in source
    assert source.count("file_counts(fname, resolved_ents, resolved_rels)") == 2


def test_recount_plans_only_wrong_rows():
    jobs = [
        {"id": "1", "case_id": "c", "batch_id": "b", "file_name": "a.dotx", "relationship_count": 23},
        {"id": "2", "case_id": "c", "batch_id": "b", "file_name": "b.dotx", "relationship_count": 13},
        {"id": "3", "case_id": "c", "batch_id": "b", "file_name": "plan.pdf", "relationship_count": 23},
    ]
    changes = planned_changes(jobs, {("c", "a.dotx"): 10, ("c", "b.dotx"): 13})
    assert [(c["id"], c["new_relationship_count"]) for c in changes] == [("1", 10), ("3", 0)]
