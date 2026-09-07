// One synthetic exclusion through the UI; restore that exact row in finally.
const path=require('path'),fs=require('fs');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/coverage-check.json'),'utf8'));
 if(fixture.case_id!=='e0da5581-a1ac-4db5-a3a9-e17021fb807a')throw Error('Unexpected synthetic fixture');
 const browser=await chromium.launch({headless:true});
 let page,rowId,restoreNeeded=false;
 const report={case_id:fixture.case_id};
 try{
  page=await browser.newPage({viewport:{width:1440,height:1200}});page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab',{name:'Transactions',exact:true}).click();
  const token=await page.evaluate(()=>localStorage.getItem('authToken'));
  const auth={Authorization:`Bearer ${token}`};
  const rowsResponse=await page.request.get(`http://127.0.0.1:58002/api/financial/ledger?case_id=${fixture.case_id}`,{headers:auth});
  const rows=await rowsResponse.json();
  const first=rows.transactions[0];
  if(first.amount_minor!=='40000'||first.ledger_status!=='admitted')throw Error('Unexpected starting row');
  rowId=first.key;
  const summary=page.getByRole('region',{name:'Current ledger summary',exact:true});
  await summary.getByText('Credits: 2100.00 GBP',{exact:true}).waitFor();
  const row=page.locator(`[data-testid="ledger-row"][data-row-key="${rowId}"]`);
  if(await row.count()!==1)throw Error('Synthetic row selection ambiguous');
  await row.getByTestId('ledger-row-action').click();
  await page.getByTestId('adjudication-reason-input').fill('Synthetic cross-view exclusion acceptance check; restore immediately afterwards.');
  restoreNeeded=true;
  await page.getByTestId('adjudication-submit').click();await page.getByRole('button',{name:'Done',exact:true}).click();
  await summary.getByText('Credits: 1700.00 GBP',{exact:true}).waitFor();
  await summary.getByText('9 included rows; 1 excluded from 10 rows in this scope.',{exact:true}).waitFor();
  for(const [tab,region,button] of [
   ['Counterparties','Ledger counterparty labels','Read ledger counterparty totals'],
   ['Trends','Ledger totals by date','Read ledger date totals']]){
    await page.getByRole('tab',{name:tab,exact:true}).click();
    const panel=page.getByRole('region',{name:region,exact:true});
    await panel.getByRole('button',{name:button,exact:true}).click();
    await panel.getByText('Credits: 1700.00 GBP · Debits: 0.00 GBP · Net postings: 1700.00 GBP',{exact:true}).waitFor();
    report[tab]=true;
  }
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();
  await (await pending).saveAs(path.join(root,'data/local-runtime/cross-view-excluded.zip'));
  report.excluded_row_id=rowId;report.transactions=true;
 }finally{
  try{
   if(restoreNeeded){
    const token=await page.evaluate(()=>localStorage.getItem('authToken'));
    const response=await page.request.post(`http://127.0.0.1:58002/api/financial/transactions/${rowId}/release?case_id=${fixture.case_id}`,{headers:{Authorization:`Bearer ${token}`},data:{reason:'Restore synthetic row after cross-view exclusion acceptance check.'}});
    const result=await response.json();if(!response.ok()||!['released','unchanged'].includes(result.outcome))throw Error('Synthetic restoration failed: '+JSON.stringify(result));
    await page.reload();await page.getByRole('tab',{name:'Transactions',exact:true}).click();
    await page.getByRole('region',{name:'Current ledger summary',exact:true}).getByText('Credits: 2100.00 GBP',{exact:true}).waitFor();
    await page.getByRole('tab',{name:'Trends',exact:true}).click();
    const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();
    await (await pending).saveAs(path.join(root,'data/local-runtime/cross-view-restored.zip'));
    report.restored=true;
   }
  }finally{await browser.close();}
 }
 fs.writeFileSync(path.join(root,'data/local-runtime/cross-view-exclusion-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
