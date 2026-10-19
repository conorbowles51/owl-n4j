// Read-only currency-total to contributing rows to original PDF acceptance.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const caseId='a2dae109-477c-4526-8642-c6a358a73479';const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);let writes=0;const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 const response=page.waitForResponse(r=>r.url().includes('/ledger-working-summary?')&&r.url().includes('include_contributions=true'));
 await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);const summary=await(await response).json();
 if(summary.contributions.length!==104||summary.included_rows!==104||summary.currencies[0].credits_minor!=='766541'||summary.currencies[0].debits_minor!=='120934')throw Error('Unexpected contributing population');
 const totals=page.getByRole('region',{name:'Working ledger totals',exact:true});await totals.getByRole('button',{name:/Net postings: .*show contributing readings/}).click();
 const region=page.getByRole('region',{name:'USD contributing readings',exact:true});const counts=[];const refs=[];
 do {const rows=region.locator('tbody tr');counts.push(await rows.count());refs.push(...await rows.locator('td:first-child').allTextContents());const next=region.getByRole('button',{name:'Next contributing readings',exact:true});if(await next.isDisabled())break;await next.click()}while(counts.length<6);
 if(JSON.stringify(counts)!==JSON.stringify([25,25,25,25,4])||new Set(refs).size!==104)throw Error('Source pagination omitted or repeated readings');
 await region.getByRole('button',{name:'Close contributing readings',exact:true}).click();await totals.getByRole('button',{name:/Credits: .*show contributing readings/}).click();
 const creditCount=summary.contributions.filter(r=>r.direction==='credit').length;await region.getByText(new RegExp(`^${creditCount} contributing readings`)).waitFor();
 const citation=page.waitForResponse(r=>r.url().includes('/source?')&&r.url().includes('/ledger/'));await region.getByRole('button',{name:/Open source/}).first().click();const source=await(await citation).json();if(source.case_id!==caseId||source.locator_state!=='stored')throw Error('Original source citation missing');
 const dialog=page.getByRole('dialog').last();await dialog.getByRole('img').first().waitFor();await page.screenshot({path:'/tmp/loupe-summary-source-original.png'});
 await page.keyboard.press('Escape');await totals.getByRole('button',{name:'Refresh working totals',exact:true}).click();await region.waitFor({state:'detached'});
 await totals.getByRole('button',{name:/Debits: .*show contributing readings/}).click();await page.getByRole('region',{name:'USD contributing readings',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-summary-source-rows.png'});
 if(writes||errors.length)throw Error(JSON.stringify({writes,errors}));const report={case_id:caseId,readings:104,pages:counts,credits_minor:'766541',debits_minor:'120934',source_transaction_id:source.transaction_id,source_page:source.locator.page,refresh_clears_selection:true,financial_writes:writes};fs.writeFileSync(path.join(root,'data/local-runtime/summary-source-ui-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
