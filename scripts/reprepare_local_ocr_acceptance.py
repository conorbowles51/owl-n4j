"""One guarded reprepare of the unreviewed local OCR acceptance upload."""
import json,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/local-runtime/ocr-geometry-reprepare.json'
CASE='5828f158-f437-4cf4-9236-ec18947e3c39'
FILE='3b7894aa-74c6-474d-affd-880f2ce48430'
if OUT.exists():raise SystemExit('Reprepare checkpoint exists; inspect it before any further processing.')
with httpx.Client(base_url='http://127.0.0.1:58002',trust_env=False,timeout=60) as c:
 r=c.post('/api/auth/login',json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'});r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
 r=c.get('/api/financial/candidate-mappings',params={'case_id':CASE});r.raise_for_status();state=r.json()
 assert state['case_id']==CASE and not state['items'] and not state['has_more'], 'Never reprepare a mapped acceptance source'
 report=dict(case_id=CASE,evidence_file_id=FILE,no_saved_candidates=True,status='starting');OUT.write_text(json.dumps(report,indent=2))
 r=c.post('/api/evidence/process/background',json={'case_id':CASE,'file_ids':[FILE],'preparation_mode':'pdf_review'});r.raise_for_status();report['preparation']=r.json();report['status']='queued';OUT.write_text(json.dumps(report,indent=2))
 job=report['preparation']['job_ids'][0]
 deadline=time.monotonic()+180
 while time.monotonic()<deadline:
  r=c.get(f'/api/engine/jobs/{job}',params={'case_id':CASE});r.raise_for_status();jobstate=r.json()
  if jobstate['status'] in ('completed','failed','cancelled'):
   report['status']=jobstate['status'];OUT.write_text(json.dumps(report,indent=2));assert jobstate['status']=='completed';break
  time.sleep(1)
 else:raise RuntimeError('Preparation still pending; inspect saved job without resubmitting')
 print(json.dumps(report))
