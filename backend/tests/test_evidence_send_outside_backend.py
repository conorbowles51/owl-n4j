"""Files sent from a script outside the backend (scripts/reprocess_failed_files.py) are sent and the run ends
cleanly, saying their statuses settle on the next sync: the job subscriber only runs inside the backend
(8 Nov, MH1: all 10 files sent, then AttributeError 'NoneType' object has no attribute 'subscribe')."""
from uuid import uuid4

import pytest

from services import evidence_processing_service as processing
from services.job_status_subscriber import JobStatusSubscriber
from tests.test_evidence_send_isolation import FakeDb, _harness


@pytest.mark.asyncio
async def test_track_jobs_without_a_running_subscriber_tracks_nothing():
    subscriber = JobStatusSubscriber()
    assert subscriber.running is False
    assert await subscriber.track_jobs(['j1'], 'case') is False
    assert subscriber._tracked == {}


@pytest.mark.asyncio
async def test_send_outside_the_backend_completes_and_says_statuses_settle_later(tmp_path, monkeypatch):
    async def engine(*, case_id, files, processing_metadata, batch_id=None):
        return [{'id': str(uuid4())} for _ in files]

    case_id, files, failed = _harness(tmp_path, monkeypatch, ['a.pdf', 'b.pdf'], engine)
    not_started = JobStatusSubscriber()  # what get_subscriber() gives a script: never started
    monkeypatch.setattr(processing, 'get_subscriber', lambda: not_started)

    result = await processing.process_db_files(FakeDb(), case_id=case_id, file_ids=[f.id for f in files])

    assert result['file_count'] == 2 and len(result['job_ids']) == 2
    assert result['live_tracking'] is False
    assert processing.NOT_TRACKED_DETAIL in result['message']
    assert not failed


def test_script_apply_with_no_subscriber_exits_0(monkeypatch, capsys):
    from collections import Counter
    from contextlib import contextmanager

    import postgres.session as session
    from scripts import reprocess_failed_files as script
    from services import evidence_failures

    case = uuid4()

    @contextmanager
    def fake_session():
        yield FakeDb()
    monkeypatch.setattr(session, '_get_session_local', lambda: fake_session)
    monkeypatch.setattr(evidence_failures, 'summary', lambda db, c: {
        'total': 1, 'file_ids': [str(uuid4())], 'by_case': {str(case): Counter({'Bad file': 1})}})
    monkeypatch.setattr(evidence_failures, 'report_lines', lambda counter: ['1 Bad file'])

    async def sent(db, *, case_id, file_ids):
        return {'message': 'Processing 0 file(s)', 'refused': [{'file_id': 'x', 'name': 'r.pdf', 'reason': 'no'}]}
    monkeypatch.setattr(processing, 'process_db_files', sent)

    assert script.main(['--case', str(case), '--apply']) == 0
    assert 'refused: r.pdf: no' in capsys.readouterr().out
