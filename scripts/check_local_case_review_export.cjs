// Read-only pending real-PDF case: export wider history without admitting readings.
const path=require('path'),fs=require('fs');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const caseId='3db2ae11-da7f-405a-a087-b465bdc9f12d';
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(20000);
  let writes=0;
  await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(url=>!url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);
  await page.getByRole('tab',{name:'Transactions',exact:true}).click();
  const region=page.getByRole('region',{name:'Export ledger analysis',exact:true});
  await region.getByRole('checkbox',{name:/Include wider case financial review history/}).check();
  await region.getByRole('checkbox',{name:'Include a paginated PDF report',exact:true}).check();
  const response=page.waitForResponse(r=>r.url().includes('/ledger-export?'));
  const download=page.waitForEvent('download');await region.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();
  const received=await response;if(!received.ok()||received.headers()['x-loupe-case-review-history']!=='true')throw Error('Wider history scope was not returned');
  await(await download).saveAs('/tmp/loupe-case-review-export.zip');
  await page.getByText('Download started: ledger snapshot and manifest.',{exact:true}).waitFor();
  await region.screenshot({path:'/tmp/loupe-case-review-controls.png'});
  if(writes)throw Error('Unexpected financial write');
  console.log(JSON.stringify({case_id:caseId,wider_history_download:true,financial_writes:0}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
