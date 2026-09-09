// Read-only acceptance: reopen the finalized real-PDF controls and their source image.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const sample=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/statement-controls-review-check.json')));
 const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});let writes=0;
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto(`http://127.0.0.1:55174/cases/${sample.case_id}/financial`);await page.getByRole('tab',{name:'Statements',exact:true}).click();await page.getByRole('button',{name:'Check statement balances',exact:true}).click();
 const pending=page.waitForResponse(r=>r.url().includes('/source?'));
 await page.getByRole('button',{name:'Inspect statement source',exact:true}).click();const response=await pending;const citation=await response.json();
 if(!response.ok()||citation.reviewed_controls.balance_convention!=='liability_owed'||citation.reviewed_controls.controls.length!==4)throw Error('Missing retained controls');
 await page.getByRole('button',{name:'Inspect opening: 6700.18 USD',exact:true}).click();await page.getByText('Original text: $6,700.18',{exact:true}).waitFor();
 const image=page.getByAltText('Page 1 of the source document',{exact:true});await image.waitFor();await image.evaluate(img=>img.decode());
 await page.screenshot({path:'/tmp/loupe-neilbyrne-retained-opening-control.png'});
 await page.getByRole('button',{name:'Inspect closing: 6637.96 USD',exact:true}).click();await page.getByText('Original text: = $6,637.96',{exact:true}).waitFor();
 await page.setViewportSize({width:850,height:1100});await page.screenshot({path:'/tmp/loupe-neilbyrne-retained-closing-control-narrow.png'});
 if(writes)throw Error('Unexpected financial writes');
 const report={case_id:sample.case_id,retained_controls:4,source_page:1,liability_sign_explained:true,financial_writes:writes};fs.writeFileSync(path.join(root,'data/local-runtime/statement-control-sources-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
