// Read-only scan of both supplied PDFs, preserving originals and unchecked scope.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);let writes=0;
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 const reports=[];
 for(const fixture of [
  {case:'c06c264c-a402-4895-a696-be634fe23629',filename:'006406-006461 Hopper Lashika 0225 esubp resp_Redacted.pdf',page:4,ranges:[[1,50],[51,56]],pages:56},
  {case:'e8ecc646-7b29-49d6-b64d-7086a9a14ad4',filename:'statements - Copy (3)_Redacted.pdf',page:3,ranges:[[1,50],[51,100],[101,108]],pages:108},
 ]){
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case}/financial`);await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();await page.getByRole('button',{name:`${fixture.filename} · page ${fixture.page}`,exact:true}).click();await page.getByRole('button',{name:'Find possible rows across PDF pages',exact:true}).click();await page.getByLabel('Propose columns on each page',{exact:true}).check();await page.getByLabel('Scan currency',{exact:true}).fill('USD');
  const scans=[];
  for(const[start,end]of fixture.ranges){
   await page.getByLabel('Scan from page',{exact:true}).fill(String(start));await page.getByLabel('Scan through page',{exact:true}).fill(String(end));const pending=page.waitForResponse(r=>r.url().includes('/page-scan?'),{timeout:120000});await page.getByRole('button',{name:'Scan selected page range',exact:true}).click();const response=await pending,data=await response.json();if(!response.ok()||data.pages.length!==end-start+1||data.applied!==false)throw Error('Incomplete scan');scans.push(data);
  }
  const rows=scans.flatMap(s=>s.pages);
  if(rows.length!==fixture.pages)throw Error('Missing pages');
  for(const p of rows){if(p.source_section&&[...p.suggestions,...p.undated_charges].some(r=>r.row_index<=p.source_section.start_row||r.row_index>=p.source_section.end_row))throw Error('Outside-section suggestion');}
  if(fixture.pages===56){
   const first=rows.find(p=>p.page_number===4),interest=rows.find(p=>p.page_number===11);
   if(!first.checked||first.chosen_columns.date_column!==0||first.chosen_columns.amount_column!==2||!first.source_section)throw Error('Scanned first statement layout not recovered');
   if(!interest.undated_charges.some(r=>r.amount_sources.some(c=>c.expected_text==='11.18')))throw Error('Date-shaped amount lost');
   await page.getByLabel('Scan from page',{exact:true}).fill('4');await page.getByLabel('Scan through page',{exact:true}).fill('4');const pending=page.waitForResponse(r=>r.url().includes('/page-scan?'));await page.getByRole('button',{name:'Scan selected page range',exact:true}).click();await pending;await page.getByText(/Printed section:/).waitFor();await page.getByText(/Printed section:/).scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-ocr-section-scan.png'});
  }else if(scans.reduce((n,s)=>n+s.suggested_rows,0)!==23||scans.reduce((n,s)=>n+s.undated_charge_rows,0)!==81)throw Error('Known complete-file nominations changed');
  reports.push({case_id:fixture.case,pages:fixture.pages,checked_pages:rows.filter(p=>p.checked).length,section_pages:rows.filter(p=>p.source_section).length,dated_suggestions:scans.reduce((n,s)=>n+s.suggested_rows,0),undated_suggestions:scans.reduce((n,s)=>n+s.undated_charge_rows,0),scans});
 }
 if(writes)throw Error('Financial write attempted');fs.writeFileSync(path.join(root,'data/local-runtime/section-page-scan-check.json'),JSON.stringify({financial_writes:0,reports},null,2));console.log(JSON.stringify({financial_writes:0,reports:reports.map(({scans,...r})=>r)}));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
