// One guarded identity-write journey on the fresh synthetic resilience case.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const output=path.join(root,'data/local-runtime/counterparty-identity-ui-check.json');
const readOnly=process.argv.includes('--read-only');
(async()=>{
 if(fs.existsSync(output)&&!readOnly)throw Error('Identity journey already started; inspect or use --read-only.');
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/current-resilience-check.json')));
 if(fixture.case_id!=='e9cafc92-85a7-497c-aec8-049157e823d0'||fixture.transaction_count!==2)throw Error('Wrong synthetic fixture');
 const report=fs.existsSync(output)?JSON.parse(fs.readFileSync(output)):{case_id:fixture.case_id,status:'started',identity_writes:0};
 const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));
 const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage({viewport:{width:1550,height:1150}});page.setDefaultTimeout(20000);
  let writes=0;
  await page.route('**/api/financial/**',async route=>{const r=route.request();if(!['GET','HEAD'].includes(r.method())){if(readOnly||!r.url().includes('/counterparty-parties?')||r.method()!=='POST'){await route.abort();throw Error('Unexpected financial write')}writes++}await route.continue()});
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  const open=async()=>{await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);await page.getByRole('tab',{name:'Counterparties',exact:true}).click();const pending=page.waitForResponse(r=>r.url().includes('/counterparty-parties?')&&r.request().method()==='GET');await page.getByRole('button',{name:'Open payment identity review',exact:true}).click();const response=await pending;if(!response.ok())throw Error('Directory failed');return response.json()};
  let state=await open();
  if(!readOnly){
   for(const row of fixture.transactions)await page.getByLabel(`Link payment ${row.ref_id}`,{exact:true}).check();
   await page.getByLabel('Payment party name',{exact:true}).fill('SYNTHETIC reviewed recipient');
   await page.getByLabel('Payment identity reason',{exact:true}).fill('Synthetic acceptance only: these two test payments are linked by an explicit investigator interpretation. The fixture source has no printed counterparty name; this is not verified recipient evidence.');
   report.write_started=true;save();const pending=page.waitForResponse(r=>r.url().includes('/counterparty-parties?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Save payment identity links',exact:true}).click();const response=await pending;state=await response.json();if(!response.ok())throw Error('Identity save failed');
   report.party_id=state.parties.find(p=>p.name==='SYNTHETIC reviewed recipient')?.id;report.identity_writes=writes;report.status='saved';save();
   await page.getByRole('status').filter({hasText:'Payment identity links saved'}).waitFor();state=await open();
  }
  if(!report.party_id||state.readings.length!==2||state.readings.some(r=>r.party?.id!==report.party_id)||state.history.length!==2)throw Error('Links or history were not retained');
  const sourceRead=page.waitForResponse(r=>r.url().includes('/source?'));await page.getByRole('button',{name:`Inspect identity source ${fixture.transactions[0].ref_id}`,exact:true}).click();const sourceResponse=await sourceRead;if(!sourceResponse.ok()||(await sourceResponse.json()).transaction_id!==fixture.transactions[0].transaction_id)throw Error('Wrong source');await page.keyboard.press('Escape');
  await page.getByLabel('Group by reviewed payment identity',{exact:true}).check();
  const pending=page.waitForResponse(r=>r.url().includes('/counterparty-party-analysis?'));await page.getByRole('button',{name:'Read ledger counterparty totals',exact:true}).click();const response=await pending,data=await response.json();if(!response.ok())throw Error('Identity analysis failed');
  if(data.counterparties.length!==1||data.counterparties[0].party.id!==report.party_id||data.counterparties[0].debits_minor!=='2468'||data.counterparties[0].credits_minor!=='0'||data.included_rows!==2)throw Error('Wrong identity totals');
  const snapshot=JSON.parse(data.snapshot_json);if(snapshot.ledger.readings.some(r=>r.row.proof_class!=='p3'||r.row.counterparty_raw!==null)||snapshot.decisions.filter(e=>e.decision==='set_counterparty_party').length!==2)throw Error('Sources or identity history changed');
  if(crypto.createHash('sha256').update(data.snapshot_json).digest('hex')!==data.snapshot_sha256)throw Error('Capture hash differs');
  const chart=page.getByRole('region',{name:'Money by reviewed counterparty',exact:true});await chart.waitFor();await chart.scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-counterparty-identity.png'});
  const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'Download reviewed counterparty analysis',exact:true}).click();const dest=path.join(root,'data/local-runtime/counterparty-identity-analysis.json');await(await downloaded).saveAs(dest);const capture=JSON.parse(fs.readFileSync(dest));if(capture.snapshot_json!==data.snapshot_json||capture.counterparties[0].party.id!==report.party_id)throw Error('Downloaded identity capture differs');
  await page.getByLabel('Analysis population',{exact:true}).selectOption('verified');const verifiedPending=page.waitForResponse(r=>r.url().includes('/counterparty-party-analysis?'));await page.getByRole('button',{name:'Read ledger counterparty totals',exact:true}).click();const verified=await(await verifiedPending).json();if(verified.included_rows!==0||verified.counterparties.length!==0)throw Error('Identity promoted P3 payments');
  report.status='verified';report.source_verified=true;report.reload_verified=true;report.analysis_download_verified=true;report.working_debits_minor='2468';report.verified_included_rows=0;report.latest_run_financial_writes=writes;save();console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
