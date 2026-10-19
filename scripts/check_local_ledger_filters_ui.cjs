// Read-only check against the isolated synthetic coverage fixture.
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
  const filters = page.getByRole('region', {name: 'Ledger filters', exact: true});
  await filters.getByLabel('Find a ledger account').fill('February gap');
  await filters.getByRole('button', {name: 'Find accounts', exact: true}).click();
  await filters.getByRole('button', {name: /Select Synthetic account with February gap/}).click();
  await filters.getByLabel('Ordering date from').fill('2026-02-01');
  await filters.getByLabel('Ordering date through').fill('2026-02-28');
  // Draft changes must leave the current answer untouched.
  await page.getByTestId('ledger-summary').filter({hasText: '10 rows'}).waitFor();
  const pending = page.waitForResponse(r => {
   const url = new URL(r.url());
   return url.pathname === '/api/financial/ledger' && url.searchParams.get('account_id') === fixture.gap_account_id && url.searchParams.get('start_date') === '2026-02-01';
  });
  await filters.getByRole('button', {name: 'Apply ledger filters', exact: true}).click();
  const response = await pending, result = await response.json();
  if (response.status() !== 200 || result.transactions.length !== 0) throw new Error('Expected an empty February answer');
  await page.getByText('No admitted rows match these filters', {exact: true}).waitFor();
  await page.getByText(/This does not establish that no transactions occurred/).waitFor();
  await page.getByTestId('ledger-filter-scope').filter({hasText: fixture.gap_account_id}).waitFor();
  const coverage = page.getByRole('region', {name: 'Coverage for applied ledger filters', exact: true});
  await coverage.getByRole('button', {name: 'Check filtered coverage', exact: true}).click();
  await coverage.getByText('GBP: 0 of 28 requested days within eligible printed bounds; 28 days uncovered.', {exact: true}).waitFor();
  await coverage.getByText('Uncovered requested dates: 2026-02-01 to 2026-02-28 (28 days).', {exact: true}).waitFor();
  await coverage.scrollIntoViewIfNeeded();
  await page.screenshot({path: '/tmp/loupe-neilbyrne-ledger-filters-ui.png'});
  await filters.getByRole('button', {name: 'Clear ledger filters', exact: true}).click();
  await page.getByTestId('ledger-summary').filter({hasText: '10 rows'}).waitFor();
  if (await coverage.count()) throw new Error('Old coverage remained after Clear');
  await filters.getByLabel('Find a ledger account').fill('enclosing');
  await filters.getByRole('button', {name: 'Find accounts', exact: true}).click();
  await filters.getByRole('button', {name: /Select .*enclosing/}).click();
  await filters.getByLabel('Ordering date from').fill('2026-02-01');
  await filters.getByLabel('Ordering date through').fill('2026-02-28');
  await filters.getByRole('button', {name: 'Apply ledger filters', exact: true}).click();
  await coverage.getByRole('button', {name: 'Check filtered coverage', exact: true}).click();
  await coverage.getByText('GBP: 28 of 28 requested days within eligible printed bounds; 0 days uncovered.', {exact: true}).waitFor();
  await coverage.getByText(/This does not establish complete transaction extraction/).waitFor();
  await coverage.scrollIntoViewIfNeeded();
  await page.screenshot({path: '/tmp/loupe-neilbyrne-filtered-coverage-ui.png'});
  const report = {gap_coverage_days: 0, enclosing_coverage_days: 28, case_id: fixture.case_id, account_id: fixture.gap_account_id, empty_february: true, clear_restores_ten: true, applied: false};
  fs.writeFileSync(path.join(root, 'data/local-runtime/ledger-filters-ui-check.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
 } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
