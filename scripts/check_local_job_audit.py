"""Actual engine Job schema audit acceptance, with every change rolled back."""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID,uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
os.environ['PYTHON_DOTENV_DISABLED']='1'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evidence-engine'))
from app.models.job import Job,JobStatus
CASE=UUID('e9cafc92-85a7-497c-aec8-049157e823d0')

async def main():
    engine=create_async_engine('postgresql+asyncpg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
    identity=uuid4()
    try:
        async with engine.connect() as connection:
            outer=await connection.begin()
            before=(await connection.execute(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),{'case':CASE})).scalar_one()
            try:
                async with AsyncSession(bind=connection,join_transaction_mode='create_savepoint') as db:
                    job=Job(id=identity,case_id=str(CASE),job_type='pdf_review',status=JobStatus.PENDING,file_path='/tmp/PRIVATE_SYNTHETIC_JOB_PATH',file_name='synthetic.pdf')
                    db.add(job);await db.flush()
                    job.status=JobStatus.EXTRACTING_TEXT;await db.flush()
                    job.progress=0.5;await db.flush()
                    job.pipeline_state={'synthetic_private_state':'DO_NOT_EXPORT_THIS_BODY'};await db.flush()
                    await db.delete(job);await db.flush()
                    rows=(await db.execute(text('SELECT payload_text FROM financial_audit_events WHERE case_id=:case AND sequence>:before ORDER BY sequence'),{'case':CASE,'before':before})).scalars().all()
                    assert len(rows)==4
                    assert all(json.loads(row)['source_table']=='jobs' for row in rows)
                    assert 'PRIVATE_SYNTHETIC_JOB_PATH' not in str(rows) and 'DO_NOT_EXPORT_THIS_BODY' not in str(rows)
                    assert json.loads(rows[-1])['after'] is None
                    async with engine.connect() as observer:
                        assert (await observer.execute(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),{'case':CASE})).scalar_one()==before
            finally:await outer.rollback()
            assert (await connection.execute(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),{'case':CASE})).scalar_one()==before
            assert (await connection.execute(text('SELECT count(*) FROM jobs WHERE id=:id'),{'id':identity})).scalar_one()==0
        print('PASS: actual engine Job insert/status/private-state/delete; four audit events; progress-only update excluded; private bodies omitted; uncommitted events invisible; all changes rolled back. No worker, model or graph operation dispatched.')
    finally:await engine.dispose()

if __name__=='__main__':asyncio.run(main())
