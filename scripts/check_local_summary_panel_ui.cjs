// Exclude and restore one row in the isolated synthetic coverage fixture only.
const path = require('path'), fs = require('fs');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
 const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/coverage-check.json'), 'utf8'));
 const browser = await chromium.launch({headless: true});
 try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1200}});
  page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await page.waitForURL(url => !url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab', {name: 'Ledger', exact: true}).click();
  await page.getByTestId('ledger-summary').filter({hasText: '10 rows'}).waitFor();
  const summary = page.getByRole('region', {name: 'Current ledger summary', exact: true});
  await summary.getByText('Credits: 2100.00 GBP', {exact: true}).waitFor();
  await page.getByTestId('ledger-row').first().getByTestId('ledger-row-action').click();
  await page.getByTestId('adjudication-reason-input').fill('Synthetic local summary refresh check. Restore immediately after verification.');
  await page.getByTestId('adjudication-submit').click();
  await page.getByRole('button', {name: 'Done', exact: true}).click();
  await summary.getByText('9 included rows; 1 excluded from 10 rows in this scope.', {exact: true}).waitFor();
  await summary.getByText('Held-out rows: 1', {exact: true}).waitFor({state: 'attached'});
  await summary.scrollIntoViewIfNeeded();
  await page.screenshot({path: '/tmp/loupe-neilbyrne-summary-panel-ui.png'});
  await page.getByRole('tab', {name: 'Held out', exact: true}).click();
  await page.getByTestId('ledger-row').first().getByTestId('ledger-row-action').click();
  await page.getByTestId('adjudication-reason-input').fill('Restore synthetic row after verifying summary invalidation.');
  await page.getByTestId('adjudication-submit').click();
  await page.getByRole('button', {name: 'Done', exact: true}).click();
  await page.getByRole('tab', {name: 'Ledger', exact: true}).click();
  await summary.getByText('Credits: 2100.00 GBP', {exact: true}).waitFor();
  await summary.getByText('10 included rows; 0 excluded from 10 rows in this scope.', {exact: true}).waitFor();
  const report = {case_id: fixture.case_id, exclusion_refresh: true, restored: true, credits_minor: '210000'};
  fs.writeFileSync(path.join(root, 'data/local-runtime/summary-panel-ui-check.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
 } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
