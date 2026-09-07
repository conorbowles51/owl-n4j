// Read-only historical comparison check using the synthetic running-balance fixture.
const path=require('path'),fs=require('fs');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const report=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/running-balance-ui-check.json'),'utf8'));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1200}});page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(url=>!url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${report.fixture.case_id}/financial`);
  await page.getByRole('tab',{name:'Decisions',exact:true}).click();
  const row=page.locator(`[data-decision-id="${report.result.adjudication_id}"]`);
  await row.getByText('Original and replacement readings',{exact:true}).click();
  await row.getByText(/Saved comparison at the time of this correction/).waitFor();
  await row.getByText('Running-balance comparison',{exact:true}).click();
  await row.getByText('Assuming source row order',{exact:true}).waitFor();
  await row.getByText(/expected 410.00 GBP, printed 400.00 GBP/).first().waitFor();
  await row.getByText('Running-balance comparison',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-balance-history-ui.png'});
  await row.getByRole('button',{name:`View source: ${report.fixture.ref_id}`,exact:true}).first().click();
  await page.getByText('This is an original reading that has been replaced.').waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('[role="dialog"] img')).some(img=>img.complete&&img.naturalWidth>0));
  await page.screenshot({path:'/tmp/loupe-neilbyrne-balance-history-source-ui.png'});
  console.log(JSON.stringify({case_id:report.fixture.case_id,decision_id:report.result.adjudication_id,result:'passed',historical_source:'passed'}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
