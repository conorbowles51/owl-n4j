// Operates only on the labelled synthetic fixture from prepare_local_header_ui.py.
const path = require('path');
const fs = require('fs');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/header-check.json'), 'utf8'));
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1200}});
    page.setDefaultTimeout(15000);
    await page.goto('http://127.0.0.1:55174/login');
    await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
    await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await page.waitForURL(url=>!url.pathname.includes('login'));
    await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
    await page.getByRole('tab',{name:'Ledger',exact:true}).click();
    await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();
    await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();
    await page.getByRole('button',{name:'synthetic-headers.pdf · page 1',exact:true}).click();
    const image = page.getByAltText('Page 1 of the source document',{exact:true});
    await image.waitFor();
    if(!await image.evaluate(img=>img.complete && img.naturalWidth>0)) throw new Error('Source image did not render');
    let writes=0;
    page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/candidate-mappings?'))writes++;});
    await page.getByLabel('Column 1 meaning',{exact:true}).selectOption('transaction_date');
    await page.getByLabel('Column 2 meaning',{exact:true}).selectOption('amount');
    const panel=page.getByRole('region',{name:'Suggest rows for review',exact:true});
    await panel.getByLabel('Date column for suggestions').selectOption('0');
    await panel.getByLabel('Amount column for suggestions').selectOption('1');
    await panel.getByLabel('Currency context for suggestions').fill('GBP');
    await panel.getByRole('button',{name:'Inspect row suggestions',exact:true}).click();
    await panel.getByText('2 suggested from 3 checked rows.',{exact:true}).waitFor();
    for(const number of [1,2,3]) if(await page.getByLabel(`Select source row ${number}`,{exact:true}).isChecked())throw Error('Suggestion automatically selected a row');
    await panel.getByRole('button',{name:'Add suggested rows to review selection',exact:true}).click();
    if(await page.getByLabel('Select source row 1',{exact:true}).isChecked())throw Error('Header selected');
    for(const number of [2,3])if(!await page.getByLabel(`Select source row ${number}`,{exact:true}).isChecked())throw Error('Explicit selection was not applied');
    if(writes!==0)throw Error('Suggestions unexpectedly persisted candidates');
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({path:'/tmp/loupe-neilbyrne-row-suggestions-ui.png'});
    const result={case_id:fixture.case_id,checked_rows:3,suggested_rows:2,explicit_selection:true,candidate_writes:writes};
    fs.writeFileSync(path.join(root,'data/local-runtime/row-suggestions-ui-check.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
