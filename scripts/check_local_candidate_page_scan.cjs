// Read-only nomination across 50 pages of the supplied PDF; no automatic row creation.
const path=require('path'),fs=require('fs'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1500,height:1100}});let writes=0;
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 const caseId='e8ecc646-7b29-49d6-b64d-7086a9a14ad4';await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);
 await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();
 await page.getByRole('button',{name:'statements - Copy (3)_Redacted.pdf · page 3',exact:true}).click();
 await page.getByRole('button',{name:'Find possible rows across PDF pages',exact:true}).click();
 await page.getByLabel('Scan through page',{exact:true}).fill('50');await page.getByLabel('Possible amount column',{exact:true}).fill('3');await page.getByLabel('Scan currency',{exact:true}).fill('USD');
 const pending=page.waitForResponse(r=>r.url().includes('/page-scan?'),{timeout:120000});await page.getByRole('button',{name:'Scan selected page range',exact:true}).click();const response=await pending;const data=await response.json();
 if(!response.ok()||data.pages.length!==50||!data.suggested_rows||data.applied!==false)throw Error(JSON.stringify(data));
 fs.writeFileSync('/tmp/loupe-page-scan-result.json',JSON.stringify(data,null,2));const first=data.pages.find(p=>p.page_number===3);if(!first.checked||first.suggestions.length!==2)throw Error('First statement payment/purchase nominations changed');
 await page.getByText(new RegExp(`${data.suggested_rows} possible rows across`)).waitFor();
 await page.getByRole('region',{name:'Scan PDF pages for possible transactions',exact:true}).screenshot({path:'/tmp/loupe-page-range-scan.png'});
 await page.getByRole('button',{name:'Inspect PDF page 6',exact:true}).click();
 if(writes)throw Error('Scan wrote financial data');
 const report={case_id:caseId,requested_pages:50,checked_pages:data.pages.filter(p=>p.checked).length,unchecked_pages:data.pages.filter(p=>!p.checked).length,suggested_rows:data.suggested_rows,first_statement_dated_suggestions:2,undated_interest_not_nominated:true,financial_writes:writes};
 fs.writeFileSync(path.join(root,'data/local-runtime/page-range-scan-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
