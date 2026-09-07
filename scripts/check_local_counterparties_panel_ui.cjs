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
  await page.getByRole('tab', {name: 'Counterparties', exact: true}).click();
  await page.getByRole('region', {name: 'Authoritative ledger counterparties', exact: true}).waitFor();
  const panel=page.getByRole('region',{name:'Ledger counterparty labels',exact:true});
  await panel.getByRole('button',{name:'Read ledger counterparty totals',exact:true}).click();
  await panel.getByText('Counterparty not recorded · GBP · 10 postings',{exact:true}).waitFor();
  await panel.getByText('Credits: 2100.00 GBP · Debits: 0.00 GBP · Net postings: 2100.00 GBP',{exact:true}).waitFor();
  await panel.getByText('Contributing readings (10)',{exact:true}).click();
  const pending=page.waitForResponse(r=>r.url().includes('/source?')&&r.url().includes('/ledger/'));
  await panel.getByRole('button',{name:'Open contributing reading 1',exact:true}).click();
  const response=await pending,result=await response.json();
  if(response.status()!==200||result.case_id!==fixture.case_id)throw new Error('Source scope incorrect');
  await page.getByRole('dialog').waitFor();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-counterparties-source-ui.png'});
  const report={case_id:fixture.case_id,counterparty_total:'210000',transaction_id:result.transaction_id,source_opened:true};
  fs.writeFileSync(path.join(root,'data/local-runtime/counterparties-panel-ui-check.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
