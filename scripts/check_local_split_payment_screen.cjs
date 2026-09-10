// Read-only acceptance against the existing synthetic network case.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1500,height:1100}});page.setDefaultTimeout(20000);let writes=0;
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 const caseId='7d7d04f7-012f-4dc4-bc03-30351f3db15a';await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);await page.getByRole('tab',{name:'Patterns',exact:true}).click();
 await page.getByLabel('Split-payment threshold amount',{exact:true}).fill('150.00');
 const pending=page.waitForResponse(r=>r.url().includes('/pattern-review?'));await page.getByRole('button',{name:'Screen captured ledger',exact:true}).click();const response=await pending,data=await response.json();
 if(!response.ok()||data.threshold_minor!=='15000'||data.threshold_currency!=='GBP')throw Error(JSON.stringify(data));
 const hits=data.hypotheses.filter(h=>h.kind==='split_payment_threshold');if(hits.length!==1||hits[0].amount_minor!=='20000'||hits[0].sources.length!==2)throw Error('Wrong split-payment group');
 const heading=page.getByRole('heading',{name:/Smaller payments reach selected threshold/});await heading.waitFor();const card=heading.locator('xpath=ancestor::article');await card.getByText('Selected threshold:',{exact:false}).waitFor();
 if(await card.getByRole('button',{name:/Inspect supporting reading/}).count()!==2)throw Error('Source buttons absent');
 await card.scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-split-payment-screen.png'});
 await page.getByLabel('Split-payment threshold amount',{exact:true}).fill('250');if(await heading.count())throw Error('Stale threshold result retained');
 const next=page.waitForResponse(r=>r.url().includes('/pattern-review?'));await page.getByRole('button',{name:'Screen captured ledger',exact:true}).click();const noHit=await(await next).json();if(noHit.hypotheses.some(h=>h.kind==='split_payment_threshold'))throw Error('Threshold not applied');
 await page.getByLabel('Split-payment threshold amount',{exact:true}).fill('0');await page.getByRole('button',{name:'Screen captured ledger',exact:true}).click();await page.getByRole('alert').filter({hasText:'positive exact threshold'}).waitFor();
 if(writes)throw Error('Unexpected ledger write');const report={case_id:caseId,threshold_minor:'15000',currency:'GBP',combined_minor:hits[0].amount_minor,sources:2,changed_threshold_clears_result:true,zero_refused:true,financial_writes:writes};fs.writeFileSync(path.join(root,'data/local-runtime/split-payment-screen-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
