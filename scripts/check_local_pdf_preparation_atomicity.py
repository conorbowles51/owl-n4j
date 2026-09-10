"""Repeatable local PostgreSQL recovery check; all fixture changes roll back.

Uses the existing synthetic resilience PDF only inside an outer transaction. Never
prepares or changes supplied real PDFs and never commits the outer transaction.
"""
import asyncio
import os
os.environ["DATABASE_URL"] = "postgresql+asyncpg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local"
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4, UUID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evidence-engine'))
from app.models.job import EvidenceDocumentText, EvidenceTableGeometry, JobStatus
from app.pipeline.extract_text import ExtractedDocument
from app.pipeline.prepare_pdf_review import prepare_pdf_review
from app.services.evidence_table_geometry import replace_evidence_table_geometry

FILE = '582d271e-c6ee-4eb1-9441-f632794e1664'
async def main():
    engine = create_async_engine('postgresql+asyncpg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
    async def snapshot(connection):
        values=[]
        for model in (EvidenceDocumentText, EvidenceTableGeometry):
            rows=(await connection.execute(select(model.__table__).where(model.evidence_file_id == FILE))).mappings().all()
            values.append(sorted([dict(row) for row in rows],key=lambda r:str(r.get('id',''))))
        return values
    async def audit_count(connection):
        return (await connection.execute(text('SELECT count(*) FROM financial_audit_events WHERE case_id=(SELECT case_id FROM evidence_files WHERE id=:file)'),{'file':UUID(FILE)})).scalar_one()
    checks=[]
    try:
        async with engine.connect() as conn:
            outer=await conn.begin()
            before=await snapshot(conn)
            audit_before=await audit_count(conn)
            if not before[0] or not before[1]:raise AssertionError('Synthetic source fixture missing')
            job=SimpleNamespace(id=str(uuid4()),source_evidence_file_id=FILE,file_name='synthetic.pdf',file_path='/tmp/unused-synthetic.pdf')
            doc=ExtractedDocument(text='SYNTHETIC atomic replacement',metadata={'file_type':'pdf','table_geometry':{'per_table':[]}})
            factory=async_sessionmaker(conn,expire_on_commit=False,join_transaction_mode='create_savepoint')
            try:
                for failure in ('after_geometry','cancelled','invalid_geometry'):
                    async def interrupted(*args, **kwargs):
                        result=await replace_evidence_table_geometry(*args, **kwargs)
                        if failure=='cancelled':raise asyncio.CancelledError()
                        if failure=='after_geometry':raise RuntimeError('SYNTHETIC injected failure')
                        return SimpleNamespace(entries_invalid=1)
                    update=AsyncMock()
                    with patch('app.pipeline.prepare_pdf_review.async_session',factory), patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock(return_value=doc)), patch('app.pipeline.prepare_pdf_review.replace_evidence_table_geometry',interrupted):
                        try:await prepare_pdf_review(job,update)
                        except (RuntimeError, ValueError, asyncio.CancelledError):pass
                        else:raise AssertionError('Expected preparation failure')
                    assert await snapshot(conn)==before, failure+' changed source generation'
                    assert await audit_count(conn)==audit_before, failure+' left an audit event'
                    assert all(call.args[1]!=JobStatus.COMPLETED for call in update.call_args_list)
                    checks.append(failure+'_preserved_original')
                with patch('app.pipeline.prepare_pdf_review.async_session',factory), patch('app.pipeline.prepare_pdf_review.extract_text',AsyncMock(return_value=doc)):
                    for _ in range(2):
                        update=AsyncMock();await prepare_pdf_review(job,update)
                        now=await snapshot(conn)
                        assert now[0][0]['content']==doc.text and not now[1]
                        assert update.call_args.args[1]==JobStatus.COMPLETED
                assert await audit_count(conn)>audit_before
                checks.append('successful_retry_replaced_text_and_geometry_together')
                checks.append('source_and_audit_events_share_transaction_outcome')
                async with engine.connect() as observer:
                    assert await snapshot(observer)==before
                checks.append('uncommitted_fixture_invisible_to_other_connections')
            finally:await outer.rollback()
            assert await snapshot(conn)==before
            assert await audit_count(conn)==audit_before
            checks.append('all_test_changes_rolled_back')
        report={'checks':checks,'persistent_source_changes':0,'ledger_writes':0}
        (ROOT/'data/local-runtime/pdf-preparation-atomicity-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:await engine.dispose()
if __name__=='__main__':asyncio.run(main())
