"""Read-only summary check against the isolated synthetic coverage fixture."""
import json
from pathlib import Path
import httpx
root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / 'data/local-runtime/coverage-check.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:58002', timeout=30) as client:
    endpoint='/api/financial/ledger-summary'
    assert client.get(endpoint, params={'case_id':fixture['case_id']}).status_code in (401,403)
    login=client.post('/api/auth/login',json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'})
    login.raise_for_status();client.headers['Authorization']='Bearer '+login.json()['access_token']
    reports={}
    for name, filters, rows, total in (
        ('case',{},10,'210000'),
        ('account',{'account_id':fixture['gap_account_id']},4,'84000'),
        ('empty',{'start_date':'2026-02-01','end_date':'2026-02-28'},0,None),
    ):
        response=client.get(endpoint,params={'case_id':fixture['case_id'],**filters})
        response.raise_for_status();result=response.json()
        assert result['available'] and result['included_rows']==rows and result['excluded_rows']==0
        assert result['applied'] is False
        if total is not None:
            assert result['currencies']==[dict(currency='GBP',rows=rows,credits_minor=total,debits_minor='0',net_minor=total)]
        else:assert result['currencies']==[]
        reports[name]=result
    (root/'data/local-runtime/ledger-summary-check.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps({'case_id':fixture['case_id'],'included_rows':10,'credits_minor':'210000','result':'passed'}))
