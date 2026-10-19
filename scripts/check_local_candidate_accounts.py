"""Synthetic concurrent provisional-account creation and authenticated retry."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4
import httpx
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session, sessionmaker
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount, FinancialTransaction, FinancialIngestionRun
from postgres.models.financial_candidates import FinancialExtractionCandidate
from postgres.models.user import User
from services.financial.candidate_reviews import read_candidate_review
from services.financial.candidate_accounts import create_candidate_account
from services.financial.decisions import Actor


def main():
    fixture=json.loads((ROOT/'data/local-runtime/candidate-check.json').read_text())
    case_id,mapping_id=UUID(fixture['case_id']),UUID(fixture['mapping_id'])
    application='loupe-account-check-'+uuid4().hex[:12]
    engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local',connect_args={'application_name':application})
    factory=sessionmaker(bind=engine)
    with factory() as db:
        candidate=db.scalar(select(FinancialExtractionCandidate).where(FinancialExtractionCandidate.mapping_id==mapping_id).order_by(FinancialExtractionCandidate.row_index))
        candidate_id=candidate.id
        original=read_candidate_review(db,case_id=case_id,candidate_id=candidate_id)
        file_id=db.scalar(select(EvidenceFile.id).where(EvidenceFile.case_id==case_id))
        user=db.scalar(select(User).where(User.email=='loupe-local@example.com'))
        actor=Actor(user.name,user.email,user.id)
    request=dict(expected_revision=original['review_revision'],label='Synthetic redacted card '+uuid4().hex[:8],currency='GBP',reason='Synthetic provisional account concurrency check')
    def create():
        return create_candidate_account(session_factory=factory,case_id=case_id,candidate_id=candidate_id,request=request,actor=actor)
    with factory() as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.execute(select(EvidenceFile.id).where(EvidenceFile.id==file_id).with_for_update()).all()
        futures=[pool.submit(create) for _ in range(2)]
        try:
            waiting,deadline=0,time.monotonic()+10
            while waiting<2 and time.monotonic()<deadline:
                with engine.connect() as connection:
                    waiting=connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name=:app AND wait_event_type='Lock'"),{'app':application})
                if waiting<2:time.sleep(.05)
            assert waiting==2,'Both creators must demonstrably wait on the source lock'
        finally:blocker.rollback()
        results=[future.result(timeout=30) for future in futures]
    assert sorted(r['created'] for r in results)==[False,True]
    assert len({r['account']['id'] for r in results})==1
    with httpx.Client(base_url='http://127.0.0.1:58002',timeout=30) as client:
        login=client.post('/api/auth/login',json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'})
        login.raise_for_status();client.headers['Authorization']='Bearer '+login.json()['access_token']
        url=f'/api/financial/candidates/{candidate_id}/provisional-account'
        response=client.post(url,params={'case_id':str(case_id)},json=request)
        response.raise_for_status();reply=response.json()
        assert reply['created'] is False and reply['account']['id']==results[0]['account']['id']
        assert reply['account']['provisional'] is True and reply['account']['identifier'] is None
        accounts=client.get('/api/financial/ledger-accounts',params={'case_id':str(case_id),'search':request['label']})
        accounts.raise_for_status();assert len(accounts.json()['items'])==1
        assert client.post(url,params={'case_id':str(case_id)},json={**request,'expected_revision':'f'*64}).status_code==409
        unchanged=client.get(f'/api/financial/candidates/{candidate_id}/review',params={'case_id':str(case_id)})
        unchanged.raise_for_status();assert unchanged.json()==original
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.case_id==case_id))==0
        for result in results:
            run=db.get(FinancialIngestionRun,UUID(result['run_id']))
            assert run.status=='completed' and run.config['request']['reason']==request['reason']
    summary=dict(case_id=str(case_id),candidate_id=str(candidate_id),account_id=reply['account']['id'],observed_lock_waiters=waiting,accounts_created=1,identical_retry='same account',review_unchanged=True,ledger_transactions=0,authenticated_http='passed')
    (ROOT/'data/local-runtime/candidate-account-check.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2));engine.dispose()

if __name__=='__main__':main()
