// Read-only source selection check against the second supplied PDF sample.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
  const intake = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/second-real-pdf-intake-check.json')));
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1100}});
    let writes = 0;
    await page.route('**/api/financial/**', async route => {
      if (!['GET','HEAD'].includes(route.request().method())) { writes++; await route.abort(); }
      else await route.continue();
    });
    await page.goto('http://127.0.0.1:55174/login');
    await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
    await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await page.waitForURL(u => !u.pathname.includes('login'));
    await page.goto(`http://127.0.0.1:55174/cases/${intake.case_id}/financial`);
    await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();
    await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();
    await page.getByRole('button',{name:`${intake.filename} · page 3`,exact:true}).click();
    await page.getByRole('button',{name:'Show source row 10, column 3',exact:true}).click();
    const source = page.getByRole('region',{name:'Original document beside row selection',exact:true});
    const img = source.getByAltText('Page 3 of the source document',{exact:true});
    await img.waitFor(); await img.evaluate(img => img.decode());
    await source.scrollIntoViewIfNeeded();
    const sourceBox = await source.boundingBox(), tableBox = await page.getByRole('table').first().boundingBox();
    if (!sourceBox || !tableBox || sourceBox.x + sourceBox.width > tableBox.x + 2) throw Error('Source and selection are not beside each other');
    if (await page.getByLabel('Select source row 10',{exact:true}).isChecked()) throw Error('Inspecting source selected a row');
    if (await page.getByRole('button',{name:'Save selected rows for review',exact:true}).isEnabled()) throw Error('Inspecting source enabled save');
    await page.screenshot({path:'/tmp/loupe-neilbyrne-source-selection-desktop.png'});
    await page.setViewportSize({width:850,height:1100});
    await source.scrollIntoViewIfNeeded();
    const narrowSource = await source.boundingBox(), narrowTable = await page.getByRole('table').first().boundingBox();
    if (!narrowSource || !narrowTable || narrowTable.y < narrowSource.y + narrowSource.height) throw Error('Source and selection do not stack');
    await page.screenshot({path:'/tmp/loupe-neilbyrne-source-selection-narrow.png'});
    if (writes) throw Error('Unexpected financial write');
    const report = {case_id:intake.case_id,page:3,desktop_side_by_side:true,narrow_stacked:true,cell_location_without_selection:true,financial_writes:writes};
    fs.writeFileSync(path.join(root,'data/local-runtime/source-selection-layout-check.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode=1; });
