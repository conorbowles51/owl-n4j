// Operates only on the labelled synthetic fixture from check_local_candidates.py.
const path = require('path');
const fs = require('fs');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/candidate-check.json'), 'utf8'));
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
    await page.getByRole('button',{name:'synthetic-candidates.pdf · page 1',exact:true}).click();
    const image = page.getByAltText('Page 1 of the source document',{exact:true});
    await image.waitFor();
    if(!await image.evaluate(img=>img.complete && img.naturalWidth>0)) throw new Error('Source image did not render');
    let originalId;
    for (let attempt=0;attempt<2;attempt++) {
      await page.getByLabel('Column 1 meaning',{exact:true}).selectOption('booking_date');
      await page.getByLabel('Column 2 meaning',{exact:true}).selectOption('amount');
      await page.getByLabel('Select source row 1',{exact:true}).check();
      if(await page.getByLabel('Select source row 2',{exact:true}).isChecked()) throw new Error('Unselected row became selected');
      if(attempt===0) await page.screenshot({path:'/tmp/loupe-neilbyrne-source-selection-ui.png'});
      const pending = page.waitForResponse(r=>r.url().includes('/candidate-mappings?') && r.request().method()==='POST');
      await page.getByRole('button',{name:'Save selected rows for review',exact:true}).click();
      const response = await pending;
      const data = await response.json();
      if(response.status()!==200 || data.applied!==false || data.candidates.length!==1 || data.candidates[0].status!=='pending') throw new Error('Unexpected candidate creation outcome');
      if(data.original.proposal.rows[0].row_index!==0 || data.candidates[0].original.cells[1].text!=='1234') throw new Error('Original source row mismatch');
      if(attempt===0) originalId=data.id;
      else if(data.id!==originalId || data.created!==false) throw new Error('Identical retry duplicated source mapping');
      await page.getByText('Rows saved. Open the saved readings below to review them.',{exact:true}).waitFor();
      if(await page.getByRole('button',{name:'Save selected rows for review',exact:true}).isEnabled()) throw new Error('Save remained enabled');
      if(attempt===0) await page.getByRole('button',{name:'Reload source and selection',exact:true}).click();
    }
    await page.getByRole('button',{name:'Review source row 1',exact:true}).click();
    await page.getByLabel('Reason for decision',{exact:true}).waitFor();
    const summary={case_id:fixture.case_id,mapping_id:originalId,selected_rows:1,source_image:'passed',identical_retry:'same mapping',status:'pending',applied:false,ui:'passed'};
    fs.writeFileSync(path.join(root,'data/local-runtime/candidate-source-ui-check.json'),JSON.stringify(summary,null,2)+'\n');
    console.log(JSON.stringify(summary));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
