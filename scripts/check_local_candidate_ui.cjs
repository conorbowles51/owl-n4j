// Uses only the labelled synthetic fixture created by check_local_candidate_reviews.py.
const path = require('path');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
const fs = require('fs');
(async () => {
 const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/candidate-review-check.json'),'utf8'));
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
  await page.getByRole('button',{name:'Open readings',exact:true}).click();
  await page.getByRole('button',{name:'Review source row 1',exact:true}).click();
  await page.getByLabel('Reason for decision',{exact:true}).fill('Synthetic browser check: reopen');
  if (await page.getByRole('button',{name:'Reopen for review',exact:true}).isEnabled()) {
  const reopen = page.waitForResponse(r=>r.url().includes('/review?') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Reopen for review',exact:true}).click();
  if((await reopen).status()!==200) throw new Error('Reopen failed');
  await page.getByText('Review recorded. Reload to see its current state and history.').waitFor();
  await page.getByRole('button',{name:'Reload review',exact:true}).click();
  }
  await page.getByLabel('Currency',{exact:true}).fill('GBP');
  await page.getByLabel('Reviewed amount',{exact:true}).fill('12.34');
  await page.getByLabel('Account',{exact:true}).selectOption(fixture.account_id);
  await page.getByLabel('Direction',{exact:true}).selectOption('debit');
  await page.getByLabel('Booking date',{exact:true}).fill('2026-02-01');
  await page.getByLabel('Description',{exact:true}).fill('Synthetic browser reviewed reading');
  await page.getByLabel('Reason for decision',{exact:true}).fill('Synthetic browser check: reviewed original source');
  await page.getByRole('button',{name:'Assess original amounts',exact:true}).click();
  await page.getByText('Numeric reading: 1234.00 GBP',{exact:true}).waitFor();
  await page.getByAltText('Page 1 of the source document',{exact:true}).first().waitFor();
  const resolve = page.waitForResponse(r=>r.url().includes('/review?') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Record resolved reading',exact:true}).click();
  const response = await resolve;
  const result = await response.json();
  if(response.status()!==200 || result.reading.amount_minor!=='1234' || result.applied!==false) throw new Error('Exact review outcome mismatch');
  await page.getByText('Review recorded. Reload to see its current state and history.').waitFor();
  await page.getByRole('button',{name:'Reload review',exact:true}).click();
  await page.getByLabel('Reviewed amount',{exact:true}).waitFor();
  await page.getByLabel('Reason for decision',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-candidate-review-ui.png'});
  console.log(JSON.stringify({case_id:fixture.case_id,candidate_id:fixture.candidate_id,status:result.status,amount_minor:result.reading.amount_minor,history_entries:result.history.length,applied:result.applied,ui:'passed'}));
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
