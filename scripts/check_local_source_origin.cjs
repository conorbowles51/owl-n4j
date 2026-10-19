// Read-only source provenance display against both supplied PDFs.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const accounts=process.argv.includes('--accounts');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1500,height:1100}});page.setDefaultTimeout(20000);let writes=0;const reports=[];
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 for(const [caseId,number] of [['c06c264c-a402-4895-a696-be634fe23629',4],['e8ecc646-7b29-49d6-b64d-7086a9a14ad4',3]]){
  await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);
  await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();
  const pending=page.waitForResponse(r=>r.url().includes('/candidate-sources/')&&r.url().includes(`/pages/${number}?`));
  await page.getByRole('button',{name:new RegExp(` · page ${number}$`)}).click();const response=await pending,data=await response.json();if(!response.ok())throw Error('Source read failed');
  const label=page.getByLabel('Stored page text origin',{exact:true});await label.waitFor();
  const expected={digital_text_layer:'PDF text layer',recognised_glyphs:'recognised from an image (OCR)',unknown:'text origin is unknown'}[data.text_origin];if(!expected||!(await label.innerText()).includes(expected))throw Error('Origin display differs');
  if(await page.getByRole('checkbox',{checked:true}).count())throw Error('Source rows selected automatically');
  let referenceCount=0;if(accounts){await page.getByRole('button',{name:'Inspect printed account references',exact:true}).click();const panel=page.getByRole('region',{name:'Printed account reference proposals',exact:true});referenceCount=await panel.getByRole('button',{name:/Inspect account reference at row/}).count();if(!referenceCount)throw Error('Known labelled account header was not proposed');await panel.getByRole('button',{name:/Inspect account reference at row/}).first().click();await page.getByRole('button',{name:'Show table location',exact:true}).waitFor();const original=page.getByRole('img',{name:`Page ${number} of the source document`,exact:true});await original.waitFor();await original.evaluate(img=>img.decode());if(await page.getByRole('checkbox',{checked:true}).count())throw Error('Reference inspection selected transaction rows');await panel.scrollIntoViewIfNeeded();}else await label.scrollIntoViewIfNeeded();await page.screenshot({path:`/tmp/loupe-source-${accounts?"accounts":"origin"}-${number}.png`});reports.push({case_id:caseId,page:number,text_origin:data.text_origin,display_verified:true,...(accounts?{reference_proposals:referenceCount,reference_locator_opened:true}: {})});
 }
 if(writes)throw Error('Unexpected financial write');fs.writeFileSync(path.join(root,`data/local-runtime/source-${accounts?'accounts':'origin'}-check.json`),JSON.stringify({sources:reports,financial_writes:0},null,2));console.log(JSON.stringify(reports));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
