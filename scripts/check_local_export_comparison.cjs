// Compare retained full real-PDF export with a fresh account-filtered capture.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const caseId='a2dae109-477c-4526-8642-c6a358a73479';
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(30000);
  let writes=0;
  await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())&&!route.request().url().includes('/ledger-export-comparison?')){writes++;await route.abort()}else await route.continue()});
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(url=>!url.pathname.includes('login'));
  const headers={Authorization:`Bearer ${await page.evaluate(()=>localStorage.getItem('authToken'))}`};
  const accounts=await(await page.request.get(`http://127.0.0.1:58002/api/financial/ledger-accounts?case_id=${caseId}`,{headers})).json();
  if(accounts.items.length!==2)throw Error('Expected two reviewed account perspectives');
  const account=accounts.items[0].id;
  const filtered=await page.request.get(`http://127.0.0.1:58002/api/financial/ledger-export?case_id=${caseId}&account_id=${account}`,{headers});
  if(!filtered.ok())throw Error('Filtered capture failed');
  fs.writeFileSync('/tmp/loupe-filtered-comparison-export.zip',await filtered.body());
  await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);await page.getByRole('tab',{name:'Transactions',exact:true}).click();
  await page.getByText('Compare saved ledger exports',{exact:true}).click();
  await page.getByLabel('Earlier ledger export',{exact:true}).setInputFiles(path.join(root,'data/local-runtime/full-document-export.zip'));
  await page.getByLabel('Later ledger export',{exact:true}).setInputFiles('/tmp/loupe-filtered-comparison-export.zip');
  const response=page.waitForResponse(r=>r.url().includes('/ledger-export-comparison?'));
  await page.getByRole('button',{name:'Compare captured exports',exact:true}).click();
  const received=await response;if(!received.ok())throw Error('Comparison failed: '+await received.text());
  const report=await received.json();
  if(report.status!=='scope_changed'||report.scope.after.account_id!==account||!report.readings.removed.length||report.readings.added.length)throw Error('Filtered comparison result differs');
  const region=page.getByRole('region',{name:'Saved export comparison',exact:true});await region.waitFor();
  const download=page.waitForEvent('download');await region.getByRole('button',{name:'Download full export comparison',exact:true}).click();await(await download).saveAs('/tmp/loupe-browser-export-comparison.json');
  if(JSON.stringify(JSON.parse(fs.readFileSync('/tmp/loupe-browser-export-comparison.json','utf8')))!==JSON.stringify(report))throw Error('Comparison download changed');
  await region.screenshot({path:'/tmp/loupe-export-comparison.png'});
  await page.getByLabel('Later ledger export',{exact:true}).setInputFiles(path.join(root,'data/local-runtime/full-document-export.zip'));
  if(await region.count())throw Error('Old comparison remained after file change');
  if(writes)throw Error('Unexpected financial write');
  console.log(JSON.stringify({case_id:caseId,scope_change_identified:true,absent_from_filtered_capture:report.readings.removed.length,changed_readings:report.readings.changed.length,exact_download:true,stale_result_cleared:true,financial_writes:0}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
