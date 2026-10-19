// Investigation/export acceptance, with one guarded note in the isolated UI import.
const fs=require('fs'),path=require('path');const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const report=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/statement-import-acceptance.json')));
 if(!report.confirmed)throw Error('No confirmed local import');
 const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage({viewport:{width:1800,height:1150}});page.setDefaultTimeout(30000);
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${report.case_id}/financial`);await page.getByRole('button',{name:'Ledger postings',exact:true}).click();await page.getByTestId('ledger-table').waitFor();
  if(!report.investigation_note_id){
   if(report.investigation_note_started)throw Error('Note request outcome needs inspection before retry');
   await page.getByRole('button',{name:'Add note',exact:true}).first().click();
   await page.getByLabel('Your transaction note',{exact:true}).fill('LOCAL acceptance: ask the account holder about this payment. This note tests the financial transaction evidence link.');
   report.investigation_note_started=true;fs.writeFileSync(path.join(root,'data/local-runtime/statement-import-acceptance.json'),JSON.stringify(report,null,2));
   const note=page.waitForResponse(r=>r.url().includes(`/workspace/${report.case_id}/entries`)&&r.request().method()==='POST');await page.getByRole('button',{name:'Save investigation note',exact:true}).click();const result=await note;const saved=await result.json();if(!result.ok() || saved.case_id!==report.case_id)throw Error('Note save not confirmed');report.investigation_note_id=saved.id;fs.writeFileSync(path.join(root,'data/local-runtime/statement-import-acceptance.json'),JSON.stringify(report,null,2));await page.getByText('Note saved.',{exact:false}).waitFor();await page.keyboard.press('Escape');
  }
  await page.getByRole('button',{name:'View source',exact:true}).first().click();
  await page.getByRole('img',{name:'Page 1 of the source document',exact:true}).waitFor();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-imported-transaction-source.png'});
  await page.keyboard.press('Escape');
  const parties=page.waitForResponse(r=>r.url().includes('/ledger-working-analysis?')&&r.url().includes('grouping=counterparty'));
  await page.getByRole('tab',{name:'Counterparties',exact:true}).click();const partyResponse=await parties;if(!partyResponse.ok())throw Error('Counterparty read failed');const party=await partyResponse.json();
  if(party.included_rows!==12 || party.counterparties.length!==2 || party.counterparties.some(p=>p.rows!==6))throw Error('Counterparty totals differ from imported statement');
  await page.getByRole('region',{name:'Authoritative ledger counterparties'}).getByText('GlobalTech Industries',{exact:true}).first().waitFor();await page.screenshot({path:'/tmp/loupe-neilbyrne-imported-counterparties.png'});
  const trends=page.waitForResponse(r=>r.url().includes('/ledger-working-analysis?')&&r.url().includes('grouping=monthly'));
  await page.getByRole('tab',{name:'Trends',exact:true}).click();const trendResponse=await trends;if(!trendResponse.ok())throw Error('Trend read failed');const trend=await trendResponse.json();
  if(trend.included_rows!==12 || trend.points.reduce((n,p)=>n+BigInt(p.credits_minor),0n)!==103500000n || trend.points.reduce((n,p)=>n+BigInt(p.debits_minor),0n)!==100000000n)throw Error('Trend totals differ from the statement');
  await page.screenshot({path:'/tmp/loupe-neilbyrne-imported-trends.png'});
  await page.getByRole('tab',{name:'Transactions',exact:true}).click();await page.getByText('Download these transactions',{exact:true}).click();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download this table view',exact:true}).click();await(await download).saveAs(path.join(root,'data/local-runtime/statement-import-table-export.zip'));
  fs.writeFileSync(path.join(root,'data/local-runtime/statement-investigation-acceptance.json'),JSON.stringify({case_id:report.case_id,source_opened:true,counterparty_groups:party.counterparties.length,transactions:trend.included_rows,credits_minor:'103500000',debits_minor:'100000000',table_export_downloaded:true},null,2));
  console.log('PASS: imported transaction opens its PDF; counterparties and monthly trends automatically load matching totals; table export downloads.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
