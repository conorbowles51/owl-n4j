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
  await page.getByRole('tab', {name: 'Transactions', exact: true}).click();
  await page.getByRole('region', {name: 'Current ledger summary', exact: true}).waitFor();
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();
  const download=await downloadPromise;
  if(download.suggestedFilename()!=='loupe-ledger-export.zip')throw new Error('Unexpected download name');
  await download.saveAs(path.join(root,'data/local-runtime/primary-ledger-export-ui.zip'));
  await page.getByText('Download started: ledger snapshot and manifest.',{exact:true}).waitFor();
  console.log(JSON.stringify({case_id:fixture.case_id,downloaded:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
