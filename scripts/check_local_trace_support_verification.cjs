// Read-only saved-package verification UI. Never prepares a new export or edits a case.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const archive='/tmp/loupe-reference-support-cli.zip',caseId='3dfbafe7-fa6b-4bdd-9af5-0e97975447b9';
 const hash=crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex');
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(30000);let writes=0,checks=0;
  await page.route('**/api/financial/**',async route=>{
   const request=route.request();
   if(request.url().includes('/trace-support-verification?')){checks++;await route.continue()}
   else if(!['GET','HEAD'].includes(request.method())){writes++;await route.abort()}
   else await route.continue();
  });
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);await page.getByRole('tab',{name:'Transactions',exact:true}).click();
  await page.getByText('Check a saved tracing audit package',{exact:true}).click();
  await page.getByLabel('Tracing audit ZIP',{exact:true}).setInputFiles(archive);
  await page.getByLabel('Previously saved SHA-256 (optional)',{exact:true}).fill(hash);
  const pending=page.waitForResponse(r=>r.url().includes('/trace-support-verification?'));
  await page.getByRole('button',{name:'Check package',exact:true}).click();const response=await pending;
  if(!response.ok())throw Error(await response.text());const result=await response.json();
  if(result.case_id!==caseId||result.archive_sha256!==hash||result.checkpoint_status!=='matches_supplied_digest'||result.status==='verified_bytes_different_rebuild')throw Error('Verification mismatch');
  const region=page.getByRole('region',{name:'Saved package verification',exact:true});await region.waitFor();
  const download=page.waitForEvent('download');await region.getByRole('button',{name:'Download verification',exact:true}).click();await(await download).saveAs('/tmp/loupe-browser-support-verification.json');
  const saved=JSON.parse(fs.readFileSync('/tmp/loupe-browser-support-verification.json','utf8'));
  if(saved.archive_sha256!==hash||saved.status!==result.status)throw Error('Downloaded result differs');
  await region.scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-support-verification-desktop.png'});
  await page.setViewportSize({width:390,height:844});await region.scrollIntoViewIfNeeded();
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Narrow page overflows');
  await page.screenshot({path:'/tmp/loupe-support-verification-mobile.png'});
  await page.getByLabel('Previously saved SHA-256 (optional)',{exact:true}).fill('0'.repeat(64));
  await page.getByRole('button',{name:'Check package',exact:true}).click();await page.getByRole('alert').filter({hasText:'differs from the previously saved digest'}).waitFor();
  if(checks!==1||writes)throw Error('Unexpected request or case write');
  const token=await page.evaluate(()=>localStorage.getItem('authToken'));
  const other=await page.request.post('http://127.0.0.1:58002/api/financial/trace-support-verification?case_id=e8ecc646-7b29-49d6-b64d-7086a9a14ad4',{headers:{Authorization:`Bearer ${token}`},multipart:{archive:{name:'support.zip',mimeType:'application/zip',buffer:fs.readFileSync(archive)}}});
  if(other.status()!==422)throw Error('Cross-case archive was not refused');
  console.log(JSON.stringify({case_id:caseId,status:result.status,download_verified:true,independent_digest_mismatch_refused_before_upload:true,cross_case_refused:true,narrow_layout:true,financial_writes:0}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
