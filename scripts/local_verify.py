"""Repeatable local setup and read-only application checks; fixed loopback targets."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
from uuid import UUID
import zipfile

import httpx
from redis import Redis

ROOT = Path(__file__).resolve().parents[1]
API = 'http://127.0.0.1:58002'
EMAIL, PASSWORD = 'loupe-local@example.com', 'Loupe-local-test-2026'


class CheckFailure(ValueError):
    pass


def require(condition, message):
    if not condition:raise CheckFailure(message)


def login(client):
    response = client.post('/api/auth/login', json={'username':EMAIL,'password':PASSWORD})
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']


def setup(client):
    status = client.get('/api/setup/status');status.raise_for_status()
    created = status.json()['needs_setup']
    if created:
        response=client.post('/api/setup/initial-user',json={'email':EMAIL,'name':'Local Tester','password':PASSWORD})
        response.raise_for_status()
    login(client)
    print('Local tester created.' if created else 'Existing local tester verified; no account or case created.')


def check(client, case_id):
    results=[]
    def run(name, operation):
        try:
            detail=operation()
            results.append(dict(check=name,passed=True,detail=detail))
        except Exception as exc:
            # Never print response bodies, credentials, tokens or source data.
            status=getattr(getattr(exc,'response',None),'status_code',None)
            results.append(dict(check=name,passed=False,error=str(exc) if isinstance(exc,CheckFailure) else f'{type(exc).__name__}'+(f' HTTP{status}' if status else '')))
    def get(url, **kwargs):
        response=client.get(url,**kwargs);response.raise_for_status();return response
    def backend():
        value=get('/health').json()
        require(value['neo4j']=='connected' and value['evidence_engine']=='ok','Backend graph/engine dependencies are unavailable.')
        return 'Backend, graph and evidence engine connected.'
    def engine():
        value=get('http://127.0.0.1:58003/health',headers={'X-API-Key':'loupe-local-service'}).json()
        required=('postgres','neo4j','chromadb','redis','ocr','storage')
        require(all(value['checks'].get(k) is True for k in required),'One or more local engine dependencies are unavailable.')
        return {k:value['checks'][k] for k in required}
    def migrations():
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text
        expected=set(ScriptDirectory.from_config(Config(str(ROOT/'backend/alembic.ini'))).get_heads())
        database=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
        try:
            with database.connect() as connection:
                actual=set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
            require(actual==expected,'Database migration head differs; run local_app.py migrate.')
            return sorted(actual)
        finally:database.dispose()
    def worker():
        with Redis.from_url('redis://127.0.0.1:56379',socket_timeout=5) as redis:
            require(redis.ping(),'Local Redis is unavailable.')
            ttl=redis.ttl('arq:queue:health-check')
            require(ttl>0,'Worker heartbeat absent; start local_app.py worker.')
        return 'Worker heartbeat present; this is not a job-processing or provider test.'
    run('frontend',lambda: {'status':get('http://127.0.0.1:55174/login').status_code})
    run('backend-services',backend)
    run('engine-and-local-ocr',engine)
    run('database-migration-head',migrations)
    run('worker-heartbeat',worker)
    run('local-login',lambda:login(client))
    if case_id:
        def financial():
            params={'case_id':case_id}
            summary=get('/api/financial/ledger-working-summary',params=params).json()
            require(summary['case_id']==case_id and summary['available'],'Financial summary is unavailable or has a different scope.')
            raw=get('/api/financial/ledger-export',params=params).content
            archive=zipfile.ZipFile(io.BytesIO(raw))
            snapshot_bytes=archive.read('ledger-snapshot.json')
            snapshot=json.loads(snapshot_bytes);manifest=json.loads(archive.read('manifest.json'))
            require(hashlib.sha256(snapshot_bytes).hexdigest()==manifest['document_sha256'],'Snapshot hash differs from its manifest.')
            require(snapshot['ledger']['case_id']==case_id and snapshot['export_ready'],'Export scope or history capture is incomplete.')
            require(snapshot['working_totals']['currencies']==summary['currencies'],'Export and current totals differ; finish editing before repeating the check.')
            for key in ('report','pdf_report'):
                if key in manifest:
                    entry=manifest[key]
                    require(hashlib.sha256(archive.read(entry['filename'])).hexdigest()==entry['sha256'],'Report hash differs from its manifest.')
            return dict(captured_readings=len(snapshot['ledger']['readings']),current_working_rows=summary['included_rows'],export_hash_verified=True)
        run('financial-summary-and-export',financial)
        for endpoint in ('statement-checks','statement-coverage','ledger-posting-graph','ledger-transfer-candidates','ledger-timeline','pattern-review','account-parties'):
            def read(endpoint=endpoint):
                value=get('/api/financial/'+endpoint,params={'case_id':case_id}).json()
                require(value['case_id']==case_id,'A financial read returned a different case.')
                return 'Case-scoped read succeeded.'
            run(endpoint,read)
    report=dict(checked_at=datetime.now(timezone.utc).isoformat(),case_id=case_id,
        scope='Local runtime and selected case reads; no fixture/review/ledger mutations.',
        external_ai='Not tested. Local launcher uses invalid provider credentials deliberately.',
        financial_case_checked=case_id is not None,passed=all(r['passed'] for r in results),checks=results)
    path=ROOT/'data/local-runtime/local-check.latest.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    for result in results:print(('PASS ' if result['passed'] else 'FAIL ')+result['check'])
    print('Report: '+str(path))
    if not case_id:print('No case selected; financial workflows were not checked. Pass --case-id to check a case.')
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('setup','check'))
    parser.add_argument('--case-id',type=UUID)
    args=parser.parse_args()
    with httpx.Client(base_url=API,timeout=45,trust_env=False) as client:
        if args.mode=='setup':setup(client);return 0
        return check(client,str(args.case_id) if args.case_id else None)

if __name__=='__main__':sys.exit(main())
