// Read-only comparison of two isolated cases containing the same supplied PDF.
const path=require('path'),fs=require('fs');const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1500,height:1100}});let writes=0;
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 const caseId='e8ecc646-7b29-49d6-b64d-7086a9a14ad4',other='2da970d0-b96b-4928-a23d-14f5e03407bb';
 await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);
 await page.getByRole('button',{name:'Choose comparison case',exact:true}).click();await page.getByLabel('Comparison case',{exact:true}).selectOption(other);
 const pending=page.waitForResponse(r=>r.url().includes('/cross-case-duplicates?'));
 await page.getByRole('button',{name:'Compare selected cases',exact:true}).click();const response=await pending;const data=await response.json();
 if(!response.ok()||data.matches.length!==1||!data.matches[0].matching_ingestion_hash||data.applied!==false)throw Error(JSON.stringify(data));
 await page.getByText(/Matching ingestion file hash/).waitFor();
 await page.getByRole('region',{name:'Cross-case document comparison',exact:true}).screenshot({path:'/tmp/loupe-cross-case-comparison.png'});
 if(writes)throw Error('Unexpected financial mutation');
 const report={case_id:caseId,comparison_case_id:other,matching_ingestion_hash:true,matching_stored_reading:data.matches[0].matching_stored_reading,financial_writes:writes};
 fs.writeFileSync(path.join(root,'data/local-runtime/cross-case-comparison-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
