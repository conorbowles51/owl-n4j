"""Read-only full supplied-statement inventory, not ledger admission or certification."""
import hashlib,json,re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import httpx
import pymupdf
root=Path(__file__).resolve().parents[1]
path=root/'data/loupe-test-pdfs/statements - Copy (3)_Redacted.pdf'
expected='f9292c6e6c360b0bb6dc1534019a682bc0e0f04f656a36f723fff60f64a27c7b'
if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('Supplied PDF bytes changed.')
case='e8ecc646-7b29-49d6-b64d-7086a9a14ad4';file='f256eda2-7ac7-46e9-855b-01a0ed0d7785'
span=re.compile(r'([A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+20\d{2})\s*[-–]\s*([A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+20\d{2})')
def date(text):return datetime.strptime(' '.join(text.replace('.','').split()),'%b %d, %Y').date()
def amount(text):
    raw=text.strip().removeprefix('=').strip().replace('$','').replace(' ','')
    if not re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}',raw):raise ValueError('Unresolved printed amount syntax')
    return int(Decimal(raw.replace(',',''))*100)
def control(table,labels):
    options=[]
    for row in table['rows']:
        cells=sorted(row['cells'],key=lambda c:c['column_index'])
        for i,label in enumerate(cells):
            if label['expected_text'].strip().lower().rstrip(':') not in labels:continue
            for cell in cells[i+1:]:
                try:value=amount(cell['expected_text'])
                except ValueError:break
                options.append({'row_index':row['row_index'],'label':label,'source':cell,'minor':str(value)})
    if len(options)!=1:raise ValueError(f'Printed control has {len(options)} possible cells')
    return options[0]
pages=[];periods={}
with pymupdf.open(path) as pdf:
 for number,page in enumerate(pdf,1):
    text=page.get_text();ranges=list(dict.fromkeys(span.findall(text)))
    entry={'page':number,'has_statement_range':len(ranges)==1,'transaction_section':'Interest Charge on Purchases' in text,'account_summary':'Account Summary' in text}
    if len(ranges)==1:
        bounds=tuple(date(v).isoformat() for v in ranges[0]);entry['bounds']=bounds
        period=periods.setdefault(bounds,{'start':bounds[0],'end':bounds[1],'summary_pages':[],'transaction_pages':[]})
        if entry['account_summary']:period['summary_pages'].append(number)
        if entry['transaction_section']:period['transaction_pages'].append(number)
    pages.append(entry)
scans=json.loads((root/'data/local-runtime/undated-page-scan-results.json').read_text())
if any(scan['case_id'] != case or scan['evidence_file_id'] != file or scan['applied'] is not False for scan in scans):
    raise SystemExit('Stored scan scope differs from the reviewed source.')
scan_pages={p['page_number']:p for scan in scans for p in scan['pages']}
if len(scan_pages) != len(pages) or sum(len(scan['pages']) for scan in scans) != len(pages) or set(scan_pages) != set(range(1, len(pages) + 1)):
    raise SystemExit('Stored scan must cover every page exactly once.')
results=[]
with httpx.Client(base_url='http://127.0.0.1:58002',timeout=60,trust_env=False) as client:
    login=client.post('/api/auth/login',json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'});login.raise_for_status();client.headers['Authorization']='Bearer '+login.json()['access_token']
    for period in periods.values():
      result=dict(period);results.append(result)
      try:
        if len(period['summary_pages'])!=1 or len(period['transaction_pages'])!=1:raise ValueError('Statement page scope is ambiguous')
        p=period['summary_pages'][0];response=client.get(f'/api/financial/candidate-sources/{file}/pages/{p}',params={'case_id':case,'table_index':0});response.raise_for_status();table=response.json()
        result['summary_source_revision']=table['source_revision'];result['opening']=control(table,('opening balance','previous balance','beginning balance'));result['closing']=control(table,('closing balance','new balance','ending balance'))
        ranges=[{'row_index':row['row_index'],'source':cell} for row in table['rows'] for cell in row['cells'] if any(tuple(date(v).isoformat() for v in match)==(period['start'],period['end']) for match in span.findall(cell['expected_text']))]
        if len(ranges)!=1:raise ValueError(f'Statement date range has {len(ranges)} possible cells')
        result['date_source']=ranges[0]
        transaction_page=period['transaction_pages'][0];scan=scan_pages[transaction_page];readings=[]
        for row in scan['suggestions']:
            value=amount(row['amount_source']['expected_text'])
            rawdate=row['date_source']['expected_text'].strip().replace('.','')
            dates=[]
            for year in {int(period['start'][:4]),int(period['end'][:4])}:
                try:parsed=datetime.strptime(rawdate+' '+str(year),'%b %d %Y').date().isoformat()
                except ValueError:continue
                if period['start']<=parsed<=period['end']:dates.append(parsed)
            if len(dates)!=1:raise ValueError('Transaction date needs manual interpretation')
            readings.append({'row_index':row['row_index'],'amount_source':row['amount_source'],'date_source':row['date_source'],'date':dates[0],'amount_minor':str(abs(value)),'direction':'credit' if value<0 else 'debit','basis':'Credit-card sign convention for this acceptance inventory; not an admitted or verified reading.'})
        for row in scan.get('undated_charges',[]):
            if len(row['amount_sources'])!=1:raise ValueError('Undated charge amount is ambiguous')
            value=amount(row['amount_sources'][0]['expected_text'])
            if value<0:raise ValueError('Undated charge sign needs review')
            readings.append({'row_index':row['row_index'],'amount_source':row['amount_sources'][0],'label_source':row['label_source'],'date':None,'amount_minor':str(value),'direction':'debit','basis':'Undated labelled charge; actual transaction date remains unknown.'})
        result['readings']=readings;result['transaction_source_revision']=scan['source_revision']
        credits=sum(int(r['amount_minor']) for r in readings if r['direction']=='credit');debits=sum(int(r['amount_minor']) for r in readings if r['direction']=='debit')
        delta=int(result['closing']['minor'])-int(result['opening']['minor'])-(debits-credits)
        result.update(status='arithmetically_agrees' if delta==0 else 'difference',credits_minor=str(credits),debits_minor=str(debits),delta_minor=str(delta),zero_amount_rows=sum(r['amount_minor']=='0' for r in readings))
      except (ValueError,KeyError,httpx.HTTPError) as exc:result.update(status='unresolved',reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
report={'case_id':case,'evidence_file_id':file,'file_sha256':expected,'pages':len(pages),'periods':results,'page_inventory':pages,'financial_writes':0,'certified_complete':False,'limitation':'Read-only acceptance inventory using stored proposals and an explicit credit-card sign convention. Arithmetic agreement does not establish complete extraction, visual correctness or account identity. No source readings or controls have been saved.'}
(root/'data/local-runtime/full-statement-inventory.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'pages':len(pages),'periods':len(results),'agree':sum(r['status']=='arithmetically_agrees' for r in results),'differences':[{'start':r['start'],'delta':r.get('delta_minor'),'reason':r.get('reason')} for r in results if r['status']!='arithmetically_agrees'],'reading_candidates':sum(len(r.get('readings',[])) for r in results),'financial_writes':0}))
