// Read-only check against the isolated synthetic coverage fixture.
const path = require('path'), fs = require('fs');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
 const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/exact-rows-check.json'), 'utf8'));
 const browser = await chromium.launch({headless: true});
 try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1200}});
  page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await page.waitForURL(url => !url.pathname.includes('login'));
  const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/financial/ledger');
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab', {name: 'Ledger', exact: true}).click();
  const response=await pending, data=await response.json();
  if (data.transactions[0].amount_minor !== '9007199254740993' || data.transactions[0].running_balance_minor !== '-9223372036854775808') throw new Error('HTTP integer strings lost precision');
  const row=page.getByTestId('ledger-row');
  await row.getByText('90,071,992,547,409.93', {exact:true}).waitFor();
  await row.getByText('-92,233,720,368,547,758.08', {exact:true}).waitFor();
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-exact-rows-ui.png'});
  await row.getByTestId('ledger-row-action').click();
  await page.getByTestId('adjudication-row').filter({hasText:'90,071,992,547,409.93'}).waitFor();
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  const report={case_id:fixture.case_id, exact_amount:data.transactions[0].amount_minor, exact_balance:data.transactions[0].running_balance_minor, result:'passed'};
  fs.writeFileSync(path.join(root,'data/local-runtime/exact-rows-ui-check.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
 } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
