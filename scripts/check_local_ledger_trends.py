"""Read-only daily/monthly trends check against the isolated synthetic coverage fixture."""
import json
from pathlib import Path
import httpx
root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / 'data/local-runtime/coverage-check.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:58002', timeout=30) as client:
    endpoint='/api/financial/ledger-trends'
    assert client.get(endpoint, params={'case_id':fixture['case_id']}).status_code in (401,403)
    login=client.post('/api/auth/login',json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'})
    login.raise_for_status();client.headers['Authorization']='Bearer '+login.json()['access_token']
    reports={}
    for grouping in ('daily','monthly'):
        params={'case_id':fixture['case_id'],'grouping':grouping}
        response=client.get(endpoint,params=params);response.raise_for_status();result=response.json()
        assert result['grouping']==grouping and result['date_basis']=='ordering_date' and result['applied'] is False
        assert result['included_rows']==10 and len(result['points'])==1
        point=result['points'][0]
        assert point['date']==('2026-01-15' if grouping=='daily' else '2026-01-01')
        assert point['credits_minor']=='210000' and point['debits_minor']=='0'
        assert len(point['transaction_ids'])==10 and len(point['source_document_ids'])==5
        rows=client.get('/api/financial/ledger',params={'case_id':fixture['case_id']}).json()['transactions']
        assert set(point['transaction_ids'])=={r['key'] for r in rows}
        empty=client.get(endpoint,params={**params,'start_date':'2026-02-01','end_date':'2026-02-28'}).json()
        assert empty['points']==[] and empty['included_rows']==0
        reports[grouping]=result
    assert client.get(endpoint,params={'case_id':fixture['case_id'],'grouping':'weekly'}).status_code==422
    (root/'data/local-runtime/ledger-trends-check.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps({'case_id':fixture['case_id'],'daily_monthly_match':True,'source_ids_match':True,'result':'passed'}))
