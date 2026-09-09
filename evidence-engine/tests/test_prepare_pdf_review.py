from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from app.pipeline.prepare_pdf_review import prepare_pdf_review
from app.models.job import JobStatus

@pytest.mark.asyncio
async def test_pdf_preparation_persists_sources_and_completes_without_ai():
    job=SimpleNamespace(id='job',source_evidence_file_id='file',file_name='bank.pdf',file_path='/tmp/bank.pdf')
    update=AsyncMock();doc=SimpleNamespace(metadata={'source':'test'})
    with patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock(return_value=doc)) as extract, patch('app.pipeline.prepare_pdf_review.async_session') as session, patch('app.pipeline.prepare_pdf_review.upsert_evidence_document_text',AsyncMock()) as text, patch('app.pipeline.prepare_pdf_review.replace_evidence_table_geometry',AsyncMock(return_value=SimpleNamespace(entries_invalid=0))) as geometry:
        await prepare_pdf_review(job,update)
        extract.assert_awaited_once();text.assert_awaited_once();geometry.assert_awaited_once()
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
    with patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock(return_value=SimpleNamespace(metadata={}))), patch('app.pipeline.prepare_pdf_review.async_session'), patch('app.pipeline.prepare_pdf_review.upsert_evidence_document_text',AsyncMock()), patch('app.pipeline.prepare_pdf_review.replace_evidence_table_geometry',AsyncMock(return_value=SimpleNamespace(entries_invalid=1))):
        with pytest.raises(ValueError):await prepare_pdf_review(job,update)
        assert all(call.args[1]!=JobStatus.COMPLETED for call in update.call_args_list)

@pytest.mark.asyncio
async def test_review_batch_bypasses_ai_policy_embedding_and_graph_pipeline():
    from app.pipeline import batch_orchestrator as batch
    job=SimpleNamespace(job_type='pdf_review',status=JobStatus.PENDING,id='job')
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[job]))))
    with patch('app.pipeline.prepare_pdf_review.prepare_pdf_review',AsyncMock()) as prepare, patch.object(batch,'load_ai_model_policy',AsyncMock()) as policy, patch.object(batch,'_extract_file',AsyncMock()) as extract:
        await batch.run_batch_pipeline('batch','case',db)
        prepare.assert_awaited_once();policy.assert_not_awaited();extract.assert_not_awaited()
