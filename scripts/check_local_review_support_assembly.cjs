// Existing synthetic tracing case; only ordinary export receipts are written.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {spawnSync}=require('child_process'),{chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const prepared=spawnSync(path.join(root,'data/local-runtime/backend-venv/bin/python'),['-c',`import json
from pathlib import Path
from tests.test_financial_trace_support_archive import TraceSupportArchiveTests
record,predictions=TraceSupportArchiveTests().review_inputs()
for name,value in [('review',record),('predictions',predictions)]:
 Path('/tmp/loupe-assembly-synthetic-'+name+'.json').write_text(json.dumps(value))`],{cwd:root,env:{...process.env,PYTHONPATH:path.join(root,'backend'),PYTHON_DOTENV_DISABLED:'1'},encoding:'utf8'});
 if(prepared.status!==0)throw Error(prepared.stderr);
 const caseId='3dfbafe7-fa6b-4bdd-9af5-0e97975447b9',browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(30000);let unexpected=0;
  await page.route('**/api/financial/**',async route=>{const request=route.request();if(!['GET','HEAD'].includes(request.method())&&!request.url().includes('/trace-support-assembly?')){unexpected++;await route.abort()}else await route.continue()});
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  const token=await page.evaluate(()=>localStorage.getItem('authToken'));
  const ledger=await page.request.get(`http://127.0.0.1:58002/api/financial/ledger-export?case_id=${caseId}&include_case_financial_history=true`,{headers:{Authorization:`Bearer ${token}`}});
  if(!ledger.ok())throw Error(await ledger.text());fs.writeFileSync('/tmp/loupe-assembly-synthetic-ledger.zip',await ledger.body());
  await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);await page.getByRole('tab',{name:'Transactions',exact:true}).click();
  await page.getByText('Assemble a review package',{exact:true}).click();
  await page.getByLabel('Saved tracing scenarios (JSON)',{exact:true}).setInputFiles(path.join(root,'data/local-runtime/resale-asset-trace-scenario.json'));
  await page.getByLabel('Saved ledger export (optional ZIP)',{exact:true}).setInputFiles('/tmp/loupe-assembly-synthetic-ledger.zip');
  await page.getByText('Attach reviewed extraction validation (optional)',{exact:true}).click();
  await page.getByLabel('Reconciled review record (JSON)',{exact:true}).setInputFiles('/tmp/loupe-assembly-synthetic-review.json');
  await page.getByLabel('Extraction predictions (JSON)',{exact:true}).setInputFiles('/tmp/loupe-assembly-synthetic-predictions.json');
  await page.getByLabel('Review package marking',{exact:true}).selectOption('confidential');
  const download=page.waitForEvent('download'),pending=page.waitForResponse(r=>r.url().includes('/trace-support-assembly?'));
  await page.getByRole('button',{name:'Prepare and download review package',exact:true}).click();const response=await pending;
  if(!response.ok())throw Error(await response.text());await(await download).saveAs('/tmp/loupe-browser-review-support.zip');
  await page.getByRole('status').filter({hasText:'Review package prepared and checked'}).waitFor();
  await page.getByRole('button',{name:'Prepare and download review package',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-review-assembly-desktop.png'});
  await page.setViewportSize({width:390,height:844});await page.getByRole('status').filter({hasText:'Review package prepared and checked'}).waitFor();
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Narrow review form overflows');
  await page.getByRole('button',{name:'Prepare and download review package',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-review-assembly-mobile.png'});
  if(unexpected)throw Error('Unexpected financial mutation');
  console.log(JSON.stringify({case_id:caseId,archive:'/tmp/loupe-browser-review-support.zip',marking:'confidential',synthetic_validation_only:true,ledger_source_mutations:0,prepared_export_receipts_recorded:true,narrow_state_preserved:true}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
