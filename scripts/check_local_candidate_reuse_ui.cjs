// Uses only the labelled synthetic fixture created by check_local_candidate_reviews.py.
const path = require('path');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
const fs = require('fs');
(async () => {
 const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/candidate-check.json'),'utf8'));
 const browser = await chromium.launch({headless:true});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:1200}});
  page.setDefaultTimeout(15000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.waitForURL(url => !url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab',{name:'Ledger',exact:true}).click();
  await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();
  await page.getByRole('button',{name:'Open readings',exact:true}).first().click();
  const checked=page.waitForResponse(r=>r.url().includes('/reuse-check?'));
  await page.getByRole('button',{name:'Check source reuse',exact:true}).click();
  const response=await checked; const result=await response.json();
  if(response.status()!==200 || result.source_reuse_pairs<1 || result.comparison_complete!==true || result.applied!==false) throw new Error('Source reuse was not reported');
  await page.getByText('The same stored row was selected more than once.',{exact:true}).first().waitFor();
  await page.getByRole('button',{name:'Check source reuse',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-source-reuse-ui.png'});
  const target=result.findings[0].left;
  const review=page.waitForResponse(r=>r.url().includes(`/candidates/${target.candidate_id}/review?`));
  await page.getByRole('button',{name:`Open first reading: source row ${target.row_index+1} (${target.status})`,exact:true}).first().click();
  const loaded=await review; const reading=await loaded.json();
  if(loaded.status()!==200 || reading.candidate_id!==target.candidate_id || reading.case_id!==fixture.case_id) throw new Error('Wrong reading opened from source finding');
  await page.getByLabel('Reason for decision',{exact:true}).waitFor();
  console.log(JSON.stringify({case_id:fixture.case_id,source_reuse_pairs:result.source_reuse_pairs,pairs_examined:result.pairs_examined,comparison_complete:result.comparison_complete,opened_candidate_id:reading.candidate_id,applied:false,ui:'passed'}));
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
