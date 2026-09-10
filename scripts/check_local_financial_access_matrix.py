"""Repeatable live permission matrix against fixed isolated local services.

Creates a temporary ordinary user and memberships, then removes them. Financial
reads/scenarios only; mutation requests deliberately have invalid empty bodies,
so a missing permission guard cannot turn this test into a financial edit.
"""
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4
import httpx
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from postgres.models.user import User
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import GlobalRole, CaseMembershipRole

case='e8ecc646-7b29-49d6-b64d-7086a9a14ad4'
file='f256eda2-7ac7-46e9-855b-01a0ed0d7785'
row='76057dd8-589f-49e6-9b07-1d5338c7c026'
network=json.loads((root/'data/local-runtime/asset-trace-scenario.json').read_text())
network_case=network['ledger_snapshot']['case_id'] if 'case_id' in network['ledger_snapshot'] else '3dfbafe7-fa6b-4bdd-9af5-0e97975447b9'
cases=[UUID(case),UUID(network_case)]
reads=[('GET',name,case,{},None) for name in (
 'ledger-export','ledger-working-summary','ledger-summary','ledger-working-analysis',
 'ledger-posting-graph','ledger-transfer-candidates','statement-checks','statement-coverage',
 'ledger-accounts','account-parties','candidate-mappings','candidate-sources','counterparty-parties','counterparty-party-analysis')]
reads += [('GET','indirect-review-methods',case,{},None),
 ('POST','indirect-review',case,{},dict(method='cash_t',currency='USD',start_date='2026-01-01',end_date='2026-12-31',subject='SYNTHETIC permission check',entries={},requirements={})),
 ('GET',f'ledger/{row}/source',case,{},None),
 ('GET','candidates/bc574f1c-576d-469a-acbe-af84a2ece523/source-readings',case,{},None),
 ('GET',f'candidate-sources/{file}/page-scan',case,dict(start_page=3,end_page=3,auto_columns='true',currency='USD'),None),
 ('POST','network-trace',network_case,{},network['inputs'])]
# Invalid bodies are intentional: permission denial must precede payload validation.
mutations=[('POST',name) for name in (
 f'transactions/{row}/quarantine',f'transactions/{row}/release',f'transactions/{row}/correction',
 f'transactions/{row}/correction-preview',f'candidate-sources/{file}/finalize',
 'candidate-mappings','account-parties','counterparty-parties',f'candidates/{uuid4()}/review')]
mutations += [('PUT',f'candidate-sources/{file}/statement-draft')]
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
user_id=uuid4();email=f'local-financial-access-{user_id}@example.invalid';report={}
def require(ok,message):
 if not ok:raise RuntimeError(message)
try:
 with Session(engine) as db:
  owner=db.scalar(select(User).where(User.email=='loupe-local@example.com'))
  require(owner is not None,'Local tester missing')
  owner_id=owner.id
  db.add(User(id=user_id,email=email,name='LOCAL TEST financial authorization',password_hash=owner.password_hash,global_role=GlobalRole.user,is_active=True));db.commit()
 with httpx.Client(base_url='http://127.0.0.1:58002',timeout=120,trust_env=False) as client:
  login=client.post('/api/auth/login',json=dict(username=email,password='Loupe-local-test-2026'));login.raise_for_status()
  client.headers['Authorization']='Bearer '+login.json()['access_token']
  def check(stage,expected,check_edits=True):
   outcomes={}
   for method,path,scope,params,body in reads:
    response=client.request(method,'/api/financial/'+path,params={'case_id':scope,**params},**({'json':body} if body is not None else {}))
    require(response.status_code==expected,f'{stage}: {method} {path}: expected {expected}, got {response.status_code}')
    outcomes[f'{method} {path}']=response.status_code
   if check_edits:
    for method,path in mutations:
     response=client.request(method,'/api/financial/'+path,params={'case_id':case},json={})
     require(response.status_code==403,f'{stage}: edit permission not denied before validation for {path}: {response.status_code}')
     outcomes[f'{method} {path}']=response.status_code
   report[stage]=outcomes
  check('non_member',403)
  with Session(engine) as db:
   for scope in cases:db.add(CaseMembership(case_id=scope,user_id=user_id,membership_role=CaseMembershipRole.collaborator,permissions={'case':{'view':False,'edit':True}},added_by_user_id=owner_id))
   db.commit()
  check('member_without_view',403,False)
  with Session(engine) as db:
   for scope in cases:db.get(CaseMembership,(scope,user_id)).permissions={'case':{'view':True,'edit':False}}
   db.commit()
  check('view_only',200)
  with Session(engine) as db:
   db.execute(delete(CaseMembership).where(CaseMembership.user_id==user_id));db.commit()
  check('revoked_same_token',403)
finally:
 with Session(engine) as db:
  db.execute(delete(CaseMembership).where(CaseMembership.user_id==user_id));db.execute(delete(User).where(User.id==user_id));db.commit()
  require(db.get(User,user_id) is None,'Temporary user cleanup failed')
 engine.dispose()
report['temporary_user_removed']=True
report['financial_mutations']=0
(root/'data/local-runtime/financial-access-matrix.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'stages':{k:len(v) for k,v in report.items() if isinstance(v,dict)},'temporary_user_removed':True,'financial_mutations':0}))
