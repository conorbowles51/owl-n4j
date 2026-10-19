// Download from the UI; no financial writes or changes to original evidence.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}});let writes=0;
  await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  const reports=[];
  for(const [name,caseId] of [['first','c06c264c-a402-4895-a696-be634fe23629'],['second','4d897cb5-b9e4-4df7-9a21-b1ba4b8bf5d7']]){
    await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);
    const include=page.getByLabel('Include original source files with fresh hash checks',{exact:true});await include.waitFor();if(await include.isChecked())throw Error('Original files unexpectedly selected by default');await include.check();
    const response=page.waitForResponse(r=>r.url().includes('/ledger-export?'));const download=page.waitForEvent('download');
    await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();
    const returned=await response;if(!returned.ok()||returned.headers()['x-loupe-source-files']!=='true')throw Error(await returned.text());
    await(await download).saveAs(path.join(root,`data/local-runtime/${name}-pdf-with-sources.zip`));
    await page.getByRole('region',{name:'Export ledger analysis',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:`/tmp/loupe-neilbyrne-${name}-source-export.png`});
    reports.push({case_id:caseId,filename:`${name}-pdf-with-sources.zip`,downloaded:true});
  }
  if(writes)throw Error('Unexpected financial write');console.log(JSON.stringify({exports:reports,financial_writes:writes}));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
