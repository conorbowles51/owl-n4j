// Read-only full supplied-document ledger, statement pagination and export check.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const saved=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/full-document-review-check.json')));
 if(saved.status!=='finalized'||saved.case_id!=='a2dae109-477c-4526-8642-c6a358a73479')throw Error('Unexpected finalization checkpoint');
 const expected={credits:0n,debits:0n};for(const r of saved.reviews)expected[r.reading.direction+'s']+=BigInt(r.reading.amount_minor);
 const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);let writes=0;const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto(`http://127.0.0.1:55174/cases/${saved.case_id}/financial`);
 await page.getByText(/104 of 104 loaded rows match/).waitFor();
 const table=page.getByTestId('ledger-table');if(await table.locator('tbody tr').count()!==50)throw Error('First ledger page missing rows');
 await page.getByRole('button',{name:'Next ledger rows',exact:true}).click();if(await table.locator('tbody tr').count()!==50)throw Error('Second ledger page missing rows');
 await page.getByRole('button',{name:'Next ledger rows',exact:true}).click();if(await table.locator('tbody tr').count()!==4)throw Error('Last ledger page missing rows');
 if(!await page.getByRole('button',{name:'Next ledger rows',exact:true}).isDisabled())throw Error('Unexpected ledger tail');
 await page.getByRole('button',{name:'Reset table view',exact:true}).click();
 await page.getByLabel('Include a paginated PDF report',{exact:true}).check();await page.getByLabel('Include original source files with fresh hash checks',{exact:true}).check();
 const download=page.waitForEvent('download',{timeout:120000});await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();await(await download).saveAs(path.join(root,'data/local-runtime/full-document-export.zip'));
 await page.getByRole('tab',{name:'Statements',exact:true}).click();let pending=page.waitForResponse(r=>r.url().includes('/statement-checks?'));await page.getByRole('button',{name:'Check statement balances',exact:true}).click();let response=await pending;const first=await response.json();
 if(!response.ok()||first.items.length!==25||!first.has_more||first.items.some(p=>p.status!=='balanced'))throw Error('First statement page failed');
 pending=page.waitForResponse(r=>r.url().includes('/statement-checks?')&&r.url().includes('offset=25'));await page.getByRole('button',{name:'Next statement checks',exact:true}).click();response=await pending;const last=await response.json();
 if(!response.ok()||last.items.length!==2||last.has_more||last.items.some(p=>p.status!=='balanced'))throw Error('Final statement page failed');
 const periods=[...first.items,...last.items];if(periods.reduce((n,p)=>n+p.zero_amount_rows,0)!==62)throw Error('Zero reading population mismatch');await page.getByText(/Includes 2 zero-amount readings/).first().waitFor();if(new Set(periods.map(p=>p.period_id)).size!==27||periods.reduce((n,p)=>n+p.counted_rows,0)!==104)throw Error('Statement rows omitted or repeated');
 await page.getByRole('region',{name:'Statement balance checks',exact:true}).getByText(/Checked at/).waitFor();await page.screenshot({path:'/tmp/loupe-full-document-statement-tail.png'});
 await page.getByRole('tab',{name:'Trends',exact:true}).click();await page.getByLabel('Analysis population',{exact:true}).selectOption('working');pending=page.waitForResponse(r=>r.url().includes('/ledger-working-analysis?'));await page.getByRole('button',{name:'Read ledger date totals',exact:true}).click();const analysis=await(await pending).json();
 if(analysis.included_rows!==104||analysis.currencies.length!==1||analysis.currencies[0].credits_minor!==String(expected.credits)||analysis.currencies[0].debits_minor!==String(expected.debits))throw Error('Working totals differ');
 await page.getByLabel('Analysis population',{exact:true}).selectOption('verified');pending=page.waitForResponse(r=>r.url().includes('/ledger-trends?'));await page.getByRole('button',{name:'Read ledger date totals',exact:true}).click();const verified=await(await pending).json();if(verified.included_rows!==0)throw Error('P3 rows promoted');
 if(writes||errors.length)throw Error(JSON.stringify({writes,errors}));
 const report={case_id:saved.case_id,readings:104,zero_charge_readings:62,nonzero_readings:42,ledger_pages:[50,50,4],statement_pages:[25,2],balanced_periods:27,distinct_provisional_accounts:Object.keys(saved.accounts).length,credits_minor:String(expected.credits),debits_minor:String(expected.debits),verified_rows:0,financial_writes:0,export_downloaded:true,statement_checks:periods,limitation:'Full supplied-file review acceptance with P3 retained; does not certify completeness of wider records or account ownership.'};
 fs.writeFileSync(path.join(root,'data/local-runtime/full-document-ui-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,statement_checks:undefined}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
