"""Bulk merge from the Table view (BACKLOG FEAT-004: "took a user 45 minutes to merge 8 duplicates").

Eight duplicates go to the engine in one request through the existing merge path: one merge job, every source's
summary, facts, insights and sources carried with its own key (so each fact stays attributed), the person's chosen
name and type passed on. More than the limit is refused, never silently cut.
"""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from routers import graph


class _Rows:
    def scalars(self):
        return self

    def all(self):
        return []


class _Db:
    def __init__(self):
        self.added, self.commits = [], 0

    def execute(self, *_args, **_kwargs):
        return _Rows()

    def add(self, row):
        row.id = row.id or uuid4()
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def refresh(self, _row):
        pass


def _duplicate(index):
    return {
        "key": f"orla-{index}", "name": "Orla Test" if index % 2 else "ORLA TEST", "type": "Person",
        "summary": f"Summary {index}", "verified_facts": [{"text": f"Fact {index}", "source_doc": f"doc-{index}.pdf"}],
        "ai_insights": [{"text": f"Insight {index}"}],
        "properties": {"source_files": [f"doc-{index}.pdf"], "source_quotes": [f"quote {index}"]},
        "connections": [{"key": f"company-{index}", "relationship": "PAID", "rel_properties": {"amount": index}}],
    }


async def _immediate(function, *args, **kwargs):
    return function(*args, **kwargs)


def _run(keys, preferred_type=None):
    endpoint = inspect.unwrap(graph.merge_entities)
    db, engine = _Db(), AsyncMock(return_value={"id": "engine-job-1"})
    details = {f"orla-{i}": _duplicate(i) for i in range(30)}
    subscriber = SimpleNamespace(track_jobs=AsyncMock())
    request = graph.MergeEntitiesRequest(case_id=str(uuid4()), entity_keys=keys, preferred_name="Orla Test",
                                         preferred_type=preferred_type)
    with patch.object(graph, "run_in_threadpool", _immediate), \
            patch.object(graph, "_acquire_merge_entity_locks", lambda *a: None), \
            patch.object(graph.neo4j_service, "get_node_details", lambda key, case_id=None: details.get(key)), \
            patch("services.evidence_engine_client.merge_entities", engine), \
            patch("services.job_status_subscriber.get_subscriber", lambda: subscriber), \
            patch.object(graph.system_log_service, "log", lambda *a, **k: None):
        result = asyncio.run(endpoint(request=request, user={"username": "jobs", "id": "u1"}, db=db))
    return result, db, engine


def test_eight_duplicates_merge_in_one_request_keeping_every_fact_attributed():
    keys = [f"orla-{i}" for i in range(8)]
    result, db, engine = _run(keys, preferred_type="Person")
    assert result["status"] == "processing" and engine.await_count == 1
    jobs = [row for row in db.added if type(row).__name__ == "MergeJob"]
    assert len(jobs) == 1 and jobs[0].source_entity_keys == keys and jobs[0].status == "processing"
    payload = engine.await_args.args[1]
    assert [entity["key"] for entity in payload["entities"]] == keys
    for index, entity in enumerate(payload["entities"]):
        assert entity["verified_facts"] == [{"text": f"Fact {index}", "source_doc": f"doc-{index}.pdf"}]
        assert entity["ai_insights"] == [{"text": f"Insight {index}"}]
        assert entity["source_files"] == [f"doc-{index}.pdf"] and entity["summary"] == f"Summary {index}"
        assert entity["relationships"][0]["target_key"] == f"company-{index}"
    assert payload["user_preferences"] == {"name": "Orla Test", "type": "Person"}


def test_more_than_the_limit_is_refused_not_cut():
    with pytest.raises(HTTPException) as refused:
        _run([f"orla-{i}" for i in range(graph.MAX_MERGE_ENTITIES + 1)])
    assert refused.value.status_code == 400 and str(graph.MAX_MERGE_ENTITIES) in refused.value.detail
    result, db, engine = _run([f"orla-{i}" for i in range(graph.MAX_MERGE_ENTITIES)])
    assert len(engine.await_args.args[1]["entities"]) == graph.MAX_MERGE_ENTITIES
