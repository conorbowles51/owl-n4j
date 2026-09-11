// Reprocess only the isolated statement-import acceptance fixture, once.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const file=path.join(root,'data/local-runtime/statement-import-acceptance.json');
(async()=>{
 const report=JSON.parse(fs.readFileSync(file));
 if(!report.confirmed || report.case_id!=='81555656-4bb9-4d9e-b2a1-6bf2b8c571d3')throw Error('Expected isolated acceptance fixture');
 const save=()=>fs.writeFileSync(file,JSON.stringify(report,null,2));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1800,height:1150}});page.setDefaultTimeout(30000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${report.case_id}/financial`);
  await page.getByRole('button',{name:'Ledger postings',exact:true}).click();
  if(!report.replacement_confirmed){
   await page.getByRole('button',{name:'Import a statement',exact:true}).click();
   await page.getByLabel('Uploaded statement').selectOption(report.reprocessed_file_id||report.file_id);
   if(!report.reprocessed_file_id){
    await page.getByRole('button',{name:'Open imported transactions',exact:true}).waitFor();
    const old=page.getByRole('button',{name:'Confirm import of 12 transactions',exact:true});
    if(await old.isEnabled())throw Error('Duplicate import not blocked');
    await page.getByText('Read the statement again',{exact:true}).click();
    const response=page.waitForResponse(r=>r.url().includes('/reprocess?')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Reprocess statement',exact:true}).click();
    const result=await response;if(!result.ok())throw Error(await result.text());
    const body=await result.json();report.reprocessed_file_id=body.evidence_file_id;report.reprocessing_job_id=body.job_id;save();
   }
   const replace=page.getByRole('checkbox',{name:/Replace the previous import/});await replace.waitFor({timeout:240000});
   const confirm=page.getByRole('button',{name:'Confirm import of 12 transactions',exact:true});
   if(await confirm.isEnabled())throw Error('Replacement not explicit');
   await replace.check();await page.getByLabel('Reason for detail corrections',{exact:true}).fill('Local acceptance: reread the unchanged synthetic statement and checked all twelve transactions against the PDF.');
   const response=page.waitForResponse(r=>r.url().includes(`/statement-import/${report.reprocessed_file_id}/confirm?`)&&r.request().method()==='POST');
   await confirm.click();const result=await response;report.replacement_receipt=await result.json();save();if(!result.ok())throw Error(JSON.stringify(report.replacement_receipt));report.replacement_confirmed=true;save();
  }
  await page.reload();await page.getByRole('button',{name:'Ledger postings',exact:true}).click();
  await page.getByTestId('ledger-summary').waitFor();
  if(!(await page.getByTestId('ledger-summary').textContent()).includes('12 rows'))throw Error('Replacement counted twice or lost transactions');
  await page.screenshot({path:'/tmp/loupe-neilbyrne-reprocessed-ledger.png'});
  report.reprocessing_ui_status='passed';save();console.log('PASS: preserved old import until explicit replacement, twelve active rows after reload.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
