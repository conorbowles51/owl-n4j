// One isolated UI-created case and one statement import. Repeats inspect only.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),{chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const reportPath=path.join(root,'data/local-runtime/statement-import-acceptance.json');
(async()=>{
 const report=fs.existsSync(reportPath)?JSON.parse(fs.readFileSync(reportPath)):{};
 const pdf=path.join(root,'data/loupe-test-pdfs/03_bank_statement_nexus.pdf');
 const hash=()=>crypto.createHash('sha256').update(fs.readFileSync(pdf)).digest('hex');
 const originalHash=hash();const save=()=>fs.writeFileSync(reportPath,JSON.stringify(report,null,2));
 const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage({viewport:{width:1800,height:1150}});page.setDefaultTimeout(30000);
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  if(!report.case_id){
   await page.goto('http://127.0.0.1:55174/cases');await page.getByRole('button',{name:'New',exact:true}).click();await page.getByPlaceholder('e.g. Operation Sunrise').fill('LOCAL: complete statement import acceptance');await page.getByPlaceholder('Brief description of the investigation...').fill('Isolated synthetic statement. Normal user controls only.');
   const response=page.waitForResponse(r=>r.url().endsWith('/api/cases')&&r.request().method()==='POST');await page.getByRole('button',{name:'Create Case',exact:true}).click();const created=await response;if(!created.ok())throw Error('Case creation failed');report.case_id=(await created.json()).id;report.original_sha256=originalHash;save();
  }
  await page.goto(`http://127.0.0.1:55174/cases/${report.case_id}/financial`);
  if(!report.confirmed){
   await page.getByRole('button',{name:'Ledger postings',exact:true}).click();await page.getByRole('button',{name:'Import a statement',exact:true}).click();
   if(!report.file_id){
    await page.getByRole('button',{name:'Upload a statement',exact:true}).click();await page.getByLabel('PDF document',{exact:true}).setInputFiles(pdf);
    const upload=page.waitForResponse(r=>r.url().includes('/evidence/upload')&&r.request().method()==='POST');const process=page.waitForResponse(r=>r.url().includes('/process/background')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Upload and read statement',exact:true}).click();const uploaded=await upload;if(!uploaded.ok())throw Error('Upload failed');report.file_id=(await uploaded.json()).files[0].id;save();const prepared=await process;report.preparation=await prepared.json();save();if(!prepared.ok())throw Error('Preparation failed');
   }else await page.getByLabel('Uploaded statement').selectOption(report.file_id);
   const confirm=page.getByRole('button',{name:'Confirm import of 12 transactions',exact:true});await confirm.waitFor({timeout:240000});
   if(await page.getByLabel('Account holder',{exact:true}).inputValue()!=='Nexus Trading Ltd')throw Error('Wrong statement holder');
   if(await page.getByLabel('Account number',{exact:true}).inputValue()!=='FCIB-7729384756')throw Error('Beneficiary account confused with statement account');
   if(!await confirm.isEnabled())throw Error('Clean statement unnecessarily blocked');
   await page.getByRole('button',{name:'View source',exact:true}).first().click();await page.getByRole('img',{name:'Page 1 of the source document',exact:true}).waitFor();
   await page.screenshot({path:'/tmp/loupe-neilbyrne-import-review.png'});
   const result=page.waitForResponse(r=>r.url().includes(`/statement-import/${report.file_id}/confirm?`)&&r.request().method()==='POST');await confirm.click();const imported=await result;report.receipt=await imported.json();save();if(!imported.ok())throw Error('Confirmation failed: '+JSON.stringify(report.receipt));report.confirmed=true;save();
  }
  await page.reload();await page.getByRole('button',{name:'Ledger postings',exact:true}).click();
  const rows=page.getByTestId('ledger-row');
  await page.getByTestId('ledger-summary').waitFor();
  if(!(await page.getByTestId('ledger-summary').textContent()).includes('12 rows'))throw Error('Twelve imported transactions not visible after reload');
  await page.getByTestId('ledger-summary').scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-neilbyrne-import-ledger.png'});
  if(hash()!==originalHash)throw Error('Original PDF changed');report.original_unchanged=true;report.status='ui_import_and_reload_passed';save();
  console.log('PASS: UI-created case, uploaded PDF, automatic account/transaction review, one confirmation, twelve rows after reload.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
