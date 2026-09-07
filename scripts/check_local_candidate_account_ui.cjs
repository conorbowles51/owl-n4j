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
  await page.getByRole('button',{name:'Review source row 1',exact:true}).click();
  await page.getByLabel('Currency',{exact:true}).fill('GBP');
  await page.getByRole('button',{name:'Set up a provisional account',exact:true}).click();
  const label='Synthetic UI card '+Date.now();
  await page.getByLabel('Provisional account label',{exact:true}).fill(label);
  await page.getByLabel('Reason for provisional account',{exact:true}).fill('Synthetic account setup: identifier unavailable');
  const created=page.waitForResponse(r=>r.url().includes('/provisional-account?') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Create provisional account',exact:true}).click();
  const accountResponse=await created;
  const account=await accountResponse.json();
  if(accountResponse.status()!==200 || !account.account.provisional || account.account.identifier!==null) throw new Error('Provisional account creation failed');
  await page.getByText('Provisional account selected. Its creation and your reason are recorded; the reading still needs a review decision.').waitFor();
  if(await page.getByLabel('Account',{exact:true}).inputValue()!==account.account.id) throw new Error('Created account was not selected');
  await page.getByLabel('Reviewed amount',{exact:true}).fill('12.34');
  await page.getByLabel('Direction',{exact:true}).selectOption('debit');
  await page.getByLabel('Booking date',{exact:true}).fill('2026-02-01');
  await page.getByLabel('Description',{exact:true}).fill('Synthetic provisional account reading');
  await page.getByLabel('Reason for decision',{exact:true}).fill('Synthetic browser resolution with provisional account');
  await page.getByRole('button',{name:'Create provisional account',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-provisional-account-ui.png'});
  const saved=page.waitForResponse(r=>r.url().includes('/review?') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Record resolved reading',exact:true}).click();
  const response=await saved; const result=await response.json();
  if(response.status()!==200 || result.reading.account_id!==account.account.id || result.reading.amount_minor!=='1234' || result.applied!==false) throw new Error('Reviewed account outcome mismatch');
  console.log(JSON.stringify({case_id:fixture.case_id,candidate_id:result.candidate_id,account_id:account.account.id,provisional:true,identifier:null,status:result.status,amount_minor:result.reading.amount_minor,applied:false,ui:'passed'}));
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
