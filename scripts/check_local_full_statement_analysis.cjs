// Read-only acceptance of saved full-statement totals, date provenance and both analysis populations.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const sample=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/full-statement-review-check.json')));
 if(sample.status!=='verified')throw Error('Full statement review is unfinished');
 const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});let writes=0;page.on('pageerror', error=>console.error('Browser error:',error.message));page.on('console', message=>{if(message.type()==='error')console.error('Console error:',message.text())});
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto(`http://127.0.0.1:55174/cases/${sample.case_id}/financial`);
 await page.getByText('Statement end · ordering only',{exact:true}).waitFor();
 const working=page.getByRole('region',{name:'Working ledger totals',exact:true});await working.getByText('Credits: 180.00 USD',{exact:true}).waitFor();await working.getByText('Debits: 117.78 USD',{exact:true}).waitFor();await working.getByText('Net postings: 62.22 USD',{exact:true}).waitFor();
 await page.getByLabel('Include a paginated PDF report',{exact:true}).check();
 const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();await(await downloaded).saveAs(path.join(root,'data/local-runtime/full-statement-pdf-export.zip'));
 await page.getByRole('tab',{name:'Trends',exact:true}).click();await page.getByLabel('Analysis population',{exact:true}).selectOption('working');
 let resultPromise=page.waitForResponse(r=>r.url().includes('/ledger-working-analysis?'));
 await page.getByRole('button',{name:'Read ledger date totals',exact:true}).click();let result=await(await resultPromise).json();
 if(result.included_rows!==3||result.points.length!==2||result.population!=='working')throw Error('Working trends disagree');
 await page.getByRole('region',{name:'Ledger totals by date',exact:true}).getByText(/Credits: 180.00 USD/).waitFor();
 await page.getByLabel('Analysis population',{exact:true}).selectOption('verified');
 resultPromise=page.waitForResponse(r=>r.url().includes('/ledger-trends?'));await page.getByRole('button',{name:'Read ledger date totals',exact:true}).click();result=await(await resultPromise).json();if(result.included_rows!==0)throw Error('Verified totals changed');
 await page.getByRole('tab',{name:'Counterparties',exact:true}).click();await page.getByLabel('Analysis population',{exact:true}).selectOption('working');
 resultPromise=page.waitForResponse(r=>r.url().includes('/ledger-working-analysis?'));await page.getByRole('button',{name:'Read ledger counterparty totals',exact:true}).click();result=await(await resultPromise).json();if(result.included_rows!==3||result.counterparties.length!==1||result.counterparties[0].label!==null)throw Error('Unlabelled source readings not preserved');
 await page.screenshot({path:'/tmp/loupe-full-statement-working-analysis.png'});
 await page.getByRole('tab',{name:'Posting graph',exact:true}).click();
 const graphResponse=page.waitForResponse(r=>r.url().includes('/ledger-posting-graph?'));
 await page.getByRole('button',{name:'Load posting graph',exact:true}).click();
 const graph=await(await graphResponse).json();if(graph.edges.length!==3||graph.population!=='working')throw Error('Posting graph differs from current ledger');
 await page.locator('canvas').waitFor().catch(async error=>{console.error(await page.locator('body').innerText());throw error});await page.getByRole('button',{name:'Fit graph',exact:true}).click();
 await page.getByRole('region',{name:'Ledger posting graph',exact:true}).screenshot({path:'/tmp/loupe-real-statement-posting-graph.png'});

 if(writes)throw Error('Unexpected financial write');console.log(JSON.stringify({case_id:sample.case_id,working_rows:3,verified_rows:0,credits_minor:'18000',debits_minor:'11778',net_minor:'6222',date_basis_visible:true,export_downloaded:true,financial_writes:writes}));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
