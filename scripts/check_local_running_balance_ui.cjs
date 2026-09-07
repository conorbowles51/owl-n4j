// Synthetic fixture only, from prepare_local_running_balance_ui.py.
const path=require('path'),fs=require('fs');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/running-balance-check.json'),'utf8'));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1200}});page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.waitForURL(url=>!url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab',{name:'Ledger',exact:true}).click();
  await page.locator(`[data-row-key="${fixture.transaction_id}"]`).getByRole('button',{name:'Correct amount',exact:true}).click();
  await page.getByLabel('Proposed amount (GBP)',{exact:true}).fill('410.00');
  const previewResponse=page.waitForResponse(r=>r.url().includes('/correction-preview?'));
  await page.getByRole('button',{name:'Preview correction',exact:true}).click();
  const response=await previewResponse,preview=await response.json();
  if(response.status()!==200||!preview.running_balances?.available)throw new Error(JSON.stringify(preview));
  const forward=preview.running_balances.interpretations[0];
  if(forward.current.mismatch_count!==0||forward.proposed.mismatch_count!==1)throw new Error('Running-balance impact incorrect');
  await page.getByText('Running-balance comparison',{exact:true}).click();
  await page.getByText('Assuming source row order',{exact:true}).waitFor();
  await page.getByText('Assuming reverse source row order',{exact:true}).waitFor();
  await page.getByText(/expected 410.00 GBP, printed 400.00 GBP/).first().waitFor();
  await page.getByText('Running-balance comparison',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-running-balance-preview-ui.png'});
  await page.getByLabel('Reason for correction',{exact:true}).fill('Synthetic running-balance impact test; neither source order nor complete coverage inferred');
  const corrected=page.waitForResponse(r=>r.url().includes('/correction?'));
  await page.getByRole('button',{name:'Record correction',exact:true}).click();
  const correctionResponse=await corrected,result=await correctionResponse.json();
  if(correctionResponse.status()!==200||result.proof_class!=='p3')throw new Error(JSON.stringify(result));
  await page.getByRole('button',{name:`View source: ${fixture.ref_id}`,exact:true}).first().click();
  await page.getByText('This is an original reading that has been replaced.').waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('[role="dialog"] img')).some(img=>img.complete&&img.naturalWidth>0));
  await page.screenshot({path:'/tmp/loupe-neilbyrne-running-balance-source-ui.png'});
  fs.writeFileSync(path.join(root,'data/local-runtime/running-balance-ui-check.json'),JSON.stringify({fixture,preview,result},null,2));
  console.log(JSON.stringify({case_id:fixture.case_id,result,comparison:'passed',source:'passed'}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
