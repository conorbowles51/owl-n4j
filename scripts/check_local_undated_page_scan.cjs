// Read-only automatic column proposals across all108 pages; no row creation.
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
 await page.getByLabel('Scan through page',{exact:true}).fill('50');await page.getByLabel('Propose columns on each page',{exact:true}).check();await page.getByLabel('Scan currency',{exact:true}).fill('USD');
 const scans=[];
 for(const[start,end]of [[1,50],[51,100],[101,108]]){
  await page.getByLabel('Scan from page',{exact:true}).fill(String(start));await page.getByLabel('Scan through page',{exact:true}).fill(String(end));
  const pending=page.waitForResponse(r=>r.url().includes('/page-scan?'),{timeout:120000});await page.getByRole('button',{name:'Scan selected page range',exact:true}).click();const response=await pending,data=await response.json();
  if(!response.ok()||data.pages.length!==end-start+1||data.auto_columns!==true||data.applied!==false)throw Error(JSON.stringify(data));
  scans.push(data);console.log(JSON.stringify({from:start,through:end,checked:data.pages.filter(p=>p.checked).length,suggested:data.suggested_rows}));
  await page.getByText(new RegExp(`${data.suggested_rows} possible rows across`)).waitFor();
 }
 const all=scans.flatMap(s=>s.pages),first=all.find(p=>p.page_number===3);
 if(!first.checked||first.suggestions.length!==2||first.chosen_columns.date_column!==0||first.chosen_columns.amount_column!==2)throw Error('Known first-statement layout was not recovered');
 if(!first.undated_charges.some(r=>r.row_index===21&&r.amount_sources.some(c=>c.expected_text==='$56.16')))throw Error('Known interest row missing');
 await page.getByLabel('Scan from page',{exact:true}).fill('3');await page.getByLabel('Scan through page',{exact:true}).fill('3');const interest=page.waitForResponse(r=>r.url().includes('/page-scan?'));await page.getByRole('button',{name:'Scan selected page range',exact:true}).click();await interest;await page.getByText('Undated row 22: Interest Charge on Purchases',{exact:true}).waitFor();await page.getByText('Undated row 22: Interest Charge on Purchases',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-undated-page-scan.png'});
 fs.writeFileSync(path.join(root,'data/local-runtime/undated-page-scan-results.json'),JSON.stringify(scans,null,2));
 if(writes)throw Error('Scan wrote financial data');
 const report={undated_charge_rows:all.reduce((n,p)=>n+(p.undated_charges||[]).length,0),known_interest_row_found:true,case_id:caseId,automatic_columns:true,requested_pages:108,checked_pages:all.filter(p=>p.checked).length,unchecked_pages:all.filter(p=>!p.checked).length,suggested_rows:scans.reduce((n,s)=>n+s.suggested_rows,0),first_statement_dated_suggestions:2,undated_readings_not_saved:true,financial_writes:writes};
 fs.writeFileSync(path.join(root,'data/local-runtime/undated-page-scan-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
