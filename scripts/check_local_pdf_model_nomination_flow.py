"""Real stored PDF cells, explicitly simulated model, rollback-only review flow."""
import sys, json, hashlib
from pathlib import Path
from uuid import UUID, uuid4
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.model_pdf_nomination import run_pdf_model_nomination, read_pdf_model_nomination
from services.financial.candidate_sources import read_candidate_source
from services.financial.candidate_store import store_pdf_candidates
from services.financial.candidate_assessment import candidate_source_readings
from services.financial.decisions import Actor
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_pdf_nominations import FinancialPdfNomination
case=UUID('3db2ae11-da7f-405a-a087-b465bdc9f12d')
file=UUID('a31e783e-84f8-415b-9d43-b0c481acc43e')
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
actor=Actor('SYNTHETIC model acceptance','synthetic@example.invalid')
attempt=uuid4();calls=[]
with engine.connect() as connection:
    outer=connection.begin()
    try:
        with Session(bind=connection,join_transaction_mode='create_savepoint') as db:
            before=db.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.case_id==case))
            source=read_candidate_source(db,case_id=case,evidence_file_id=file,page_number=4)
            row=next(r for r in source['rows'] if r['row_index']==40)
            assert next(c for c in row['cells'] if c['column_index']==3)['expected_text']=='14.00'
            request=dict(request_id=str(attempt),page_number=4,source_revision=source['source_revision'])
            arguments={'model':'synthetic-model','messages':[{'role':'user','content':'SIMULATED provenance fixture, not provider traffic'}]}
            transport=dict(schema_version='loupe.pdf_model_transport/1',status='captured',request_arguments=arguments,
                request_arguments_sha256=hashlib.sha256(json.dumps(arguments,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
                adapter_sha256='a'*64,response_metadata={'reported_model':'synthetic-reported-model'},limitation='SIMULATED transport metadata only; no provider was called.')
            def simulated(*args):
                calls.append(True)
                return json.dumps({'rows':[{'row_index':40,'columns':[{'column_index':0,'meaning':'date'},{'column_index':3,'meaning':'amount'}],'reason':'SIMULATED transport acceptance; not an external model conclusion.'}]}),{'transport':transport}
            with patch('services.ai_model_policy.get_workload_model',return_value=('test','synthetic-model')):
                run=run_pdf_model_nomination(db,case_id=case,evidence_file_id=file,request=request,actor=actor,call_model=simulated)
                assert run['status']=='completed' and run['request']['execution_mode']=='simulated_test'
                assert run==run_pdf_model_nomination(db,case_id=case,evidence_file_id=file,request=request,actor=actor,call_model=simulated)
            proposal=dict(schema_version='pdf-grid-mapping-v1',case_id=str(case),evidence_file_id=str(file),page_number=4,table_index=0,source_revision=source['source_revision'],nomination_id=str(attempt),columns=[{'column_index':i,'meaning': 'date' if i==0 else 'amount' if i==3 else 'unknown'} for i in source['columns']],rows=[dict(row_index=40,cells=[{k:c[k] for k in ('column_index','expected_text')} for c in row['cells']])])
            saved=store_pdf_candidates(db,case_id=case,proposal=proposal,actor=actor)
            assert len(saved['candidates'])==1 and saved['candidates'][0]['status']=='pending'
            review=candidate_source_readings(db,case_id=case,candidate_id=UUID(saved['candidates'][0]['id']))
            assert review['model_nomination']['request']['execution_mode']=='simulated_test'
            assert store_pdf_candidates(db,case_id=case,proposal=proposal,actor=actor)['id']==saved['id']
            assert db.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.case_id==case))==before
            from services.financial.ledger_review_history import capture_pdf_review_history
            history=capture_pdf_review_history(db,case_id=case,evidence_file_ids=[file])
            exported=next(m for m in history['mappings'] if m['id']==saved['id'])
            model=exported['snapshot']['nomination_snapshot']
            assert model['result']['transport']==transport
            from services.financial.review_methods import pdf_review_methods
            methods=pdf_review_methods({'pdf_review_history':{'mappings':[exported]}})
            assert methods['methods'][0]['model']['provider_reported_model']=='synthetic-reported-model'
            assert model['result']['raw_response']==run['result']['raw_response']
            assert model['request']['system_context']==run['request']['system_context']
            Path('/tmp/loupe-simulated-nomination-response.json').write_text(json.dumps(run))
            assert len(calls)==1
            print('PASS: real source cells; simulated transport once; durable result; pending review; retained provenance and export snapshot; idempotent save; unchanged ledger')
    finally: outer.rollback()
with Session(engine) as db: assert db.get(FinancialPdfNomination,attempt) is None
engine.dispose()
print('All nomination and review writes rolled back. No external model called.')
