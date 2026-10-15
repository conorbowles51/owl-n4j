from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.pipeline.prepare_pdf_review import prepare_pdf_review
from app.models.job import JobStatus

@pytest.mark.asyncio
@pytest.mark.parametrize('reading_mode', ['automatic', 'page_images'])
async def test_pdf_preparation_persists_sources_and_completes_without_ai(reading_mode):
    job=SimpleNamespace(id='job',source_evidence_file_id='file',file_name='bank.pdf',file_path='/tmp/bank.pdf',pipeline_state={'pdf_reading_mode':reading_mode})
    update=AsyncMock();doc=SimpleNamespace(metadata={'source':'test'})
    with patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock(return_value=doc)) as extract, patch('app.pipeline.prepare_pdf_review.async_session') as session, patch('app.pipeline.prepare_pdf_review.upsert_evidence_document_text',AsyncMock()) as text, patch('app.pipeline.prepare_pdf_review.replace_evidence_table_geometry',AsyncMock(return_value=SimpleNamespace(entries_invalid=0))) as geometry:
        session.return_value.__aenter__.return_value.begin = MagicMock(return_value=AsyncMock())
        await prepare_pdf_review(job,update)
        assert text.call_args.kwargs['commit'] is False
        assert geometry.call_args.kwargs['commit'] is False
        extract.assert_awaited_once();text.assert_awaited_once();geometry.assert_awaited_once()
        assert extract.call_args.kwargs['pdf_reading_mode'] == reading_mode
        assert update.call_args.kwargs['quality_report']['pdf_reading_mode'] == reading_mode
        assert update.call_args.args[1] == JobStatus.COMPLETED
        assert update.call_args.kwargs['quality_report']['transactions_admitted']==0

@pytest.mark.asyncio
@pytest.mark.parametrize('filename,source',[('image.png','file'),('bank.pdf',None)])
async def test_refuses_non_pdf_or_unregistered_source(filename,source):
    with patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock()) as extract:
        with pytest.raises(ValueError):await prepare_pdf_review(SimpleNamespace(file_name=filename,source_evidence_file_id=source),AsyncMock())
        extract.assert_not_awaited()

@pytest.mark.asyncio
async def test_geometry_failure_never_reports_ready():
    job=SimpleNamespace(id='job',source_evidence_file_id='file',file_name='bank.pdf',file_path='/tmp/bank.pdf');update=AsyncMock()
    with patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock(return_value=SimpleNamespace(metadata={}))), patch('app.pipeline.prepare_pdf_review.async_session') as session, patch('app.pipeline.prepare_pdf_review.upsert_evidence_document_text',AsyncMock()), patch('app.pipeline.prepare_pdf_review.replace_evidence_table_geometry',AsyncMock(return_value=SimpleNamespace(entries_invalid=1))):
        transaction = AsyncMock()
        session.return_value.__aenter__.return_value.begin = MagicMock(return_value=transaction)
        with pytest.raises(ValueError):await prepare_pdf_review(job,update)
        assert transaction.__aexit__.call_args.args[0] is ValueError
        assert all(call.args[1]!=JobStatus.COMPLETED for call in update.call_args_list)

@pytest.mark.asyncio
async def test_review_batch_bypasses_ai_policy_embedding_and_graph_pipeline():
    from app.pipeline import batch_orchestrator as batch
    job=SimpleNamespace(job_type='pdf_review',status=JobStatus.PENDING,id='job')
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[job]))))
    with patch('app.pipeline.prepare_pdf_review.prepare_pdf_review',AsyncMock()) as prepare, patch.object(batch,'load_ai_model_policy',AsyncMock()) as policy, patch.object(batch,'_extract_file',AsyncMock()) as extract:
        await batch.run_batch_pipeline('batch','case',db)
        prepare.assert_awaited_once();policy.assert_not_awaited();extract.assert_not_awaited()

@pytest.mark.asyncio
async def test_cancelled_review_batch_marks_unfinished_jobs_and_reraises():
    import asyncio
    from app.pipeline import batch_orchestrator as batch
    job=SimpleNamespace(job_type='pdf_review',status=JobStatus.PENDING,id='job')
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[job]))))
    with patch('app.pipeline.prepare_pdf_review.prepare_pdf_review',AsyncMock(side_effect=asyncio.CancelledError)), patch.object(batch,'_force_fail_unfinished_batch_rows',AsyncMock()) as failed:
        with pytest.raises(asyncio.CancelledError):await batch.run_batch_pipeline('batch','case',db)
        failed.assert_awaited_once_with('batch','PDF preparation was interrupted before completion')


class DeadlockDetectedError(Exception):
    sqlstate = '40P01'


class WrappedDBError(Exception):
    """The shape SQLAlchemy raises: the driver's error on ``orig``."""
    def __init__(self, orig):
        super().__init__(str(orig))
        self.orig = orig


@pytest.mark.asyncio
async def test_a_deadlocked_write_is_retried_and_other_errors_are_not():
    from app.services.db_retry import retry_transient, is_transient_db_error
    assert is_transient_db_error(WrappedDBError(DeadlockDetectedError('deadlock detected')))
    assert not is_transient_db_error(ValueError('Some PDF source locations could not be stored'))
    calls = []
    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise WrappedDBError(DeadlockDetectedError('deadlock detected'))
        return 'stored'
    assert await retry_transient(flaky, base_delay=0) == 'stored'
    assert len(calls) == 3
    async def broken():
        raise ValueError('not transient')
    with pytest.raises(ValueError):
        await retry_transient(broken, base_delay=0)
    async def always():
        raise WrappedDBError(DeadlockDetectedError('deadlock detected'))
    with pytest.raises(WrappedDBError):
        await retry_transient(always, attempts=2, base_delay=0)


@pytest.mark.asyncio
async def test_a_progress_message_lost_to_a_deadlock_never_fails_the_file():
    """Live: 30 files in 72 h failed whole on a deadlocked progress update."""
    job=SimpleNamespace(id='job',source_evidence_file_id='file',file_name='bank.pdf',file_path='/tmp/bank.pdf',pipeline_state={})
    async def update(job_id, status, *args, **kwargs):
        if status == JobStatus.EXTRACTING_TEXT and args and args[0] > 0:
            raise WrappedDBError(DeadlockDetectedError('deadlock detected'))
    recorder = AsyncMock(side_effect=update)
    async def extract(*args, progress_callback=None, **kwargs):
        await progress_callback(SimpleNamespace(completed=1, total=2, message='Page 1 of 2'))
        return SimpleNamespace(metadata={})
    with patch('app.pipeline.prepare_pdf_review.extract_text', side_effect=extract), patch('app.pipeline.prepare_pdf_review.async_session') as session, patch('app.pipeline.prepare_pdf_review.upsert_evidence_document_text',AsyncMock()), patch('app.pipeline.prepare_pdf_review.replace_evidence_table_geometry',AsyncMock(return_value=SimpleNamespace(entries_invalid=0))):
        session.return_value.__aenter__.return_value.begin = MagicMock(return_value=AsyncMock())
        await prepare_pdf_review(job, recorder)
    assert recorder.call_args.args[1] == JobStatus.COMPLETED
