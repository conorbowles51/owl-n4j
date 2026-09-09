// Upload one supplied PDF into a new isolated review case; never alter the original.
const path=require('path'),fs=require('fs'),crypto=require('crypto');const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const reportPath=path.join(root,'data/local-runtime/real-pdf-intake-check.json');
(async()=>{const previous=fs.existsSync(reportPath)?JSON.parse(fs.readFileSync(reportPath)):null;if(previous&&previous.preparation)throw Error("Preparation already submitted; inspect saved job without resubmission");const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 const headers={Authorization:`Bearer ${await page.evaluate(()=>localStorage.getItem('authToken'))}`};
 let caseId=previous?.case_id;
 if(!caseId){const created=await page.request.post('http://127.0.0.1:58002/api/cases',{headers,data:{title:'LOCAL ACCEPTANCE — supplied PDF review',description:'Isolated offline workflow test with a copy of supplied evidence.'}});if(!created.ok())throw Error('Case creation failed');caseId=(await created.json()).id;}
 const filename='006406-006461 Hopper Lashika 0225 esubp resp_Redacted.pdf';const original=path.join(root,'data/loupe-test-pdfs',filename);const digest=()=>crypto.createHash('sha256').update(fs.readFileSync(original)).digest('hex');const originalHash=digest();
 const report=previous??{case_id:caseId,filename,original_sha256:originalHash,status:'case_created'};fs.writeFileSync(reportPath,JSON.stringify(report,null,2));
 await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();if(previous?.upload){await page.getByRole('button',{name:'Find uploaded PDFs',exact:true}).click();await page.getByRole('button',{name:`Use uploaded PDF: ${filename} (unprocessed)`,exact:true}).click();}else await page.getByLabel('PDF document',{exact:true}).setInputFiles(original);
 const uploadResponse=previous?.upload?null:page.waitForResponse(r=>r.url().includes('/evidence/upload')&&r.request().method()==='POST');const processResponse=page.waitForResponse(r=>r.url().includes('/process/background')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Prepare PDF for review',exact:true}).click();if(uploadResponse){const upload=await uploadResponse;report.upload=await upload.json();fs.writeFileSync(reportPath,JSON.stringify(report,null,2));if(!upload.ok())throw Error('Upload failed');}
 const process=await processResponse;report.preparation=await process.json();report.status='queued';fs.writeFileSync(reportPath,JSON.stringify(report,null,2));if(!process.ok())throw Error('Preparation failed '+JSON.stringify(report.preparation));
 await page.getByRole('button',{name:'Choose prepared PDF rows',exact:true}).waitFor({timeout:240000});report.status='source_ready';
 await page.getByRole('button',{name:'Choose prepared PDF rows',exact:true}).click();await page.getByRole('button',{name:`${filename} · page 1`,exact:true}).waitFor();
 if(digest()!==originalHash)throw Error('Original PDF changed');report.original_unchanged=true;report.ui_reaches_source_selection=true;fs.writeFileSync(reportPath,JSON.stringify(report,null,2));await page.screenshot({path:'/tmp/loupe-neilbyrne-real-pdf-intake.png'});console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
