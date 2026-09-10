// Read-only real-PDF acceptance: current working totals, verified exclusions and export.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    let writes = 0;
    await page.route('**/api/financial/**', async route => {
      if (!['GET', 'HEAD'].includes(route.request().method())) { writes++; await route.abort(); }
      else await route.continue();
    });
    await page.goto('http://127.0.0.1:55174/login');
    await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
    await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL(u => !u.pathname.includes('login'));
    const results = [];
    for (const [name, id, excluded] of [
      ['preview', 'ccae1db4-43f8-4f93-b5b8-b744e4d50af9', 0],
      ['corrected', 'ea81df83-814c-4f9e-b3a8-3a989190b920', 1],
    ]) {
      await page.goto(`http://127.0.0.1:55174/cases/${id}/financial`);
      const working = page.getByRole('region', { name: 'Working ledger totals', exact: true });
      await working.getByText('Credits: 180.00 USD', { exact: true }).waitFor();
      await working.getByText('Debits: 61.62 USD', { exact: true }).waitFor();
      await working.getByText('Net postings: 118.38 USD', { exact: true }).waitFor();
      await working.getByText(`2 included rows; ${excluded} excluded from ${2 + excluded} rows in this scope.`, { exact: true }).waitFor();
      const verified = page.getByRole('region', { name: 'Current ledger summary', exact: true });
      await verified.getByText(`0 included rows; ${2 + excluded} excluded from ${2 + excluded} rows in this scope.`, { exact: true }).waitFor();
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Download ledger snapshot', exact: true }).click();
      await (await download).saveAs(path.join(root, `data/local-runtime/${name}-working-export.zip`));
      await working.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/loupe-${name}-working-totals.png` });
      results.push({ case_id: id, credits_minor: '18000', debits_minor: '6162', net_minor: '11838', included: 2, excluded });
    }
    if (writes) throw Error('Unexpected financial write');
    console.log(JSON.stringify({ results, financial_writes: writes }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
