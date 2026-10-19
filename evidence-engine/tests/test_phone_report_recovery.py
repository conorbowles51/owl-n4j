"""Pause inside graph writing, reopen durable progress and preserve identities."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.pipeline.cellebrite import ingestion, neo4j_client
from app.pipeline.cellebrite.models import CellebriteReport, CaseInfo, ParsedModel
from app.pipeline.cellebrite.recovery import Recovery
from app.services import ingestion_checkpoints as checkpoints


class Graph:
    def __init__(self):
        self.nodes = {}; self.anchor = None; self.closed = 0
        self.calls = []; self._driver = self
    def run_query(self, query, **params):
        self.calls.append((query, params))
        if 'RETURN r.ingestion_run_id' in query:
            return [{'run_id': self.anchor.get('ingestion_run_id')}] if self.anchor else []
        if 'MERGE (r:PhoneReport' in query:
            if self.anchor is None: self.anchor = params['create_props'].copy()
            else: self.anchor.update(params['match_props'])
        if 'MERGE (n:' in query:
            self.nodes.setdefault(params['key'], params['props'].copy())
        return []
    @contextmanager
    def session(self): yield self
    def run(self, *args, **kwargs): return []
    def close(self): self.closed += 1


class Parser:
    xml_counts_by_type = {'VisitedPage': 450}
    def __init__(self, *args, **kwargs): pass
    def parse_header(self): return CellebriteReport(case_info=CaseInfo(case_number='synthetic', evidence_number='one'))
    def parse_tagged_files(self): return []
    def stream_models(self, **kwargs):
        yield [ParsedModel(model_type='VisitedPage', model_id=f'{index:012d}', fields={'Url': f'https://example.test/{index}'}) for index in range(450)]


async def never_pause(): return False


@pytest.mark.asyncio
async def test_resume_replays_only_partial_block_and_preserves_graph_edits_and_anchor_id(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoints.settings, 'storage_path', str(tmp_path / 'saved'))
    report = tmp_path / 'report'; report.mkdir()
    xml = report / 'report.xml'; xml.write_text('<report xmlns="http://pa.cellebrite.com/report/2.0"/>')
    graph = Graph()
    monkeypatch.setattr(neo4j_client, 'Neo4jClient', lambda: graph)
    monkeypatch.setattr(ingestion, 'CellebriteXMLParser', Parser)
    monkeypatch.setattr(ingestion, '_backfill_nearest_location', lambda *a, **kw: dict(calls_tagged=0, messages_tagged=0, emails_tagged=0, window_minutes=15))
    scope, case = str(uuid4()), str(uuid4())
    pause = True
    def boundary():
        if pause and len(graph.nodes) >= 225: raise checkpoints.IngestionPaused()
    with pytest.raises(checkpoints.IngestionPaused):
        async with checkpoints.checkpoint_scope(scope, case, never_pause):
            recovery = Recovery(xml, boundary)
            recovery.save(phase='cleanup_complete')
            ingestion.ingest_cellebrite_report(report, case, recovery=recovery, pause_check=boundary)
    assert graph.closed == 1 and len(graph.nodes) == 225
    assert recovery.state['next_model'] == 200
    graph.nodes['page-000000000210']['name'] = 'Investigator edit retained'
    original_id = graph.nodes['page-000000000210']['id']
    anchor_id = graph.anchor['id']
    before = len(graph.calls); pause = False
    async with checkpoints.checkpoint_scope(scope, case, never_pause):
        reopened = Recovery(xml, boundary)
        result = ingestion.ingest_cellebrite_report(report, case, recovery=reopened, pause_check=boundary)
        assert reopened.state['next_model'] == 450
    assert result['status'] == 'success' and result['visited_pages_created'] == 450
    assert len(graph.nodes) == 450 and graph.closed == 2
    assert graph.nodes['page-000000000210']['name'] == 'Investigator edit retained'
    assert graph.nodes['page-000000000210']['id'] == original_id and graph.anchor['id'] == anchor_id
    retried_keys = [params['key'] for query, params in graph.calls[before:] if 'MERGE (n:' in query]
    assert len(retried_keys) == 250 and retried_keys[0] == 'page-000000000200'
    assert result['reconciliation']['summary']['types_under'] == 0
    xml.write_text('changed source')
    async with checkpoints.checkpoint_scope(scope, case, never_pause):
        with pytest.raises(ValueError, match='source has changed'): Recovery(xml, lambda: None)


@pytest.mark.asyncio
async def test_resuming_cannot_repopulate_a_report_replaced_by_another_run(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoints.settings, 'storage_path', str(tmp_path / 'saved'))
    report = tmp_path / 'report'; report.mkdir()
    xml = report / 'report.xml'; xml.write_text('<report xmlns="http://pa.cellebrite.com/report/2.0"/>')
    graph = Graph(); graph.anchor = {'ingestion_run_id': 'another run'}
    monkeypatch.setattr(neo4j_client, 'Neo4jClient', lambda: graph)
    monkeypatch.setattr(ingestion, 'CellebriteXMLParser', Parser)
    async with checkpoints.checkpoint_scope(str(uuid4()), str(uuid4()), never_pause):
        recovery = Recovery(xml, lambda: None); recovery.save(phase='writing', next_model=200)
        with pytest.raises(ValueError, match='replaced or removed'):
            ingestion.ingest_cellebrite_report(report, str(uuid4()), recovery=recovery)
    assert not graph.nodes and graph.closed == 1


def test_streaming_parser_can_pause_before_loading_the_whole_xml(tmp_path):
    from app.pipeline.cellebrite.parser import CellebriteXMLParser
    source = tmp_path / 'report.xml'
    source.write_text('<project>' + '<item/>' * 2000 + '</project>')
    calls = []
    def boundary():
        calls.append(1)
        if len(calls) == 2: raise checkpoints.IngestionPaused()
    parser = CellebriteXMLParser(source, pause_check=boundary)
    with pytest.raises(checkpoints.IngestionPaused): list(parser._events())
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_replacement_cleanup_is_not_repeated_when_a_run_resumes(tmp_path, monkeypatch):
    import sys
    from app.pipeline import cellebrite_ingestion as pipeline
    from app.pipeline.cellebrite import detection
    monkeypatch.setattr(checkpoints.settings, 'storage_path', str(tmp_path / 'saved'))
    monkeypatch.setattr(pipeline, '_ensure_backend_imports', lambda: None)
    report = tmp_path / 'report'; report.mkdir()
    (report / 'report.xml').write_text('<report xmlns="http://pa.cellebrite.com/report/2.0"/>')
    @contextmanager
    def db(): yield SimpleNamespace()
    cleaned = []
    monkeypatch.setitem(sys.modules, 'postgres.session', SimpleNamespace(get_background_session=db))
    monkeypatch.setitem(sys.modules, 'services.evidence_db_storage', SimpleNamespace(EvidenceDBStorage=SimpleNamespace(
        add_log=lambda *a, **kw: None, delete_by_cellebrite_report_key=lambda *a: cleaned.append('files'))))
    monkeypatch.setitem(sys.modules, 'services.neo4j_service', SimpleNamespace(neo4j_service=SimpleNamespace(
        delete_phone_report=lambda *a: cleaned.append('graph'))))
    monkeypatch.setattr(detection, 'check_cellebrite_report', lambda *a, **kw: {
        'suitable': True, 'duplicate': True, 'report_key': 'report', 'existing': {'report_key': 'report'}})
    attempts = []
    def ingest(**kwargs):
        recovery = kwargs['recovery']; attempts.append(recovery.state.get('next_model', 0))
        if len(attempts) == 1:
            recovery.save(phase='writing', next_model=200)
            raise checkpoints.IngestionPaused()
        return {'status': 'success', 'total_nodes': 450}
    monkeypatch.setattr(ingestion, 'ingest_cellebrite_report', ingest)
    case, scope = str(uuid4()), str(uuid4())
    def run():
        return pipeline._run_cellebrite_ingestion_sync(folder_path=report, case_id=case, owner='synthetic',
            force=True, created_by_id=None, evidence_folder_id=None, log_callback=lambda message: None)
    with pytest.raises(checkpoints.IngestionPaused):
        async with checkpoints.checkpoint_scope(scope, case, never_pause): run()
    async with checkpoints.checkpoint_scope(scope, case, never_pause): assert run()['status'] == 'success'
    async with checkpoints.checkpoint_scope(scope, case, never_pause): assert run()['total_nodes'] == 450
    assert cleaned == ['graph', 'files'] and attempts == [0, 200]


@pytest.mark.asyncio
async def test_shutdown_waits_for_sync_writer_to_stop_before_releasing_the_job(tmp_path, monkeypatch):
    import asyncio
    import threading
    import time
    from unittest.mock import AsyncMock
    from app.models.job import JobStatus
    from app.pipeline import cellebrite_ingestion as pipeline
    started, stopped = threading.Event(), threading.Event()
    def run(**kwargs):
        started.set()
        try:
            while True:
                kwargs['pause_check']()
                time.sleep(.01)
        finally: stopped.set()
    monkeypatch.setattr(pipeline, '_run_cellebrite_ingestion_sync', run)
    monkeypatch.setattr(checkpoints, 'pause_boundary', AsyncMock())
    update = AsyncMock(); monkeypatch.setattr(pipeline, '_update_job', update)
    job = SimpleNamespace(id=uuid4(), case_id=str(uuid4()), file_path=str(tmp_path), merge_payload={}, source_folder_id=None,
        progress=.4, pause_requested=False, paused=False, resumable=True)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: job)))
    task = asyncio.create_task(pipeline.run_cellebrite_pipeline(str(job.id), db))
    try:
        while not started.is_set(): await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert stopped.is_set() and job.paused and job.pause_requested
        assert update.call_args.args[1] == JobStatus.PENDING
    finally:
        if not task.done(): task.cancel()
