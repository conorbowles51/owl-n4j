// One pending source-bound OCR selection; --read-only repeats inspection only.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const output=path.join(root,'data/local-runtime/ocr-source-review-check.json');const readOnly=process.argv[2]==='--read-only';
(async()=>{if(fs.existsSync(output)&&!readOnly)throw Error('Writer checkpoint exists; use --read-only');
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/ocr-located-pdf-intake-check.json')));if(fixture.status!=='source_ready'||fixture.case_id!=='3db2ae11-da7f-405a-a087-b465bdc9f12d')throw Error('Unexpected intake');
 const report=readOnly?JSON.parse(fs.readFileSync(output)):{case_id:fixture.case_id,status:'starting'};const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));
 const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);let writes=0;
 await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){writes++;if(readOnly){await route.abort();return}}await route.continue()});
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();
 for(const number of [26,51]){await page.getByRole('button',{name:'Next source pages',exact:true}).click();await page.getByRole('button',{name:`${fixture.filename} · page ${number}`,exact:true}).waitFor();}
 const pending=page.waitForResponse(r=>r.url().includes('/pages/51?'));await page.getByRole('button',{name:`${fixture.filename} · page 51`,exact:true}).click();const source=await(await pending).json();
 const found=source.rows.flatMap(r=>r.cells.filter(c=>c.expected_text==='500.00').map(c=>({row:r,cell:c})));
 if(found.length!==1||source.text_origin!=='recognised_glyphs'||source.geometry_source!=='cell_rectangles')throw Error('OCR source is not precisely located');
 const {row,cell}=found[0];if(cell.locator.kind!=='page_rectangle'||cell.locator.page!==51||!row.cells.some(c=>c.expected_text==='0.00'&&c.column_index!==cell.column_index))throw Error('Amount/fee boxes were merged');
 await page.getByRole('button',{name:`Show source row ${row.row_index+1}, column ${cell.column_index+1}`,exact:true}).click();
 const image=page.getByAltText('Page 51 of the source document',{exact:true});await image.waitFor();await image.evaluate(img=>img.decode());await page.getByRole('button',{name:'Show highlighted value',exact:true}).click();await image.scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-ocr-amount-source.png'});
 if(!readOnly){
  report.source_revision=source.source_revision;report.source_cell=cell;report.source_row=row.row_index;report.evidence_file_id=source.evidence_file_id;save();
  await page.getByLabel(`Column ${cell.column_index+1} meaning`,{exact:true}).selectOption('amount');
  await page.getByLabel(`Select source row ${row.row_index+1}`,{exact:true}).check();
  const response=page.waitForResponse(r=>r.url().includes('/candidate-mappings?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Save selected rows for review',exact:true}).click();const mapped=await response,data=await mapped.json();if(!mapped.ok()||data.candidates.length!==1)throw Error('OCR candidate save failed');report.mapping_id=data.id;report.candidate_id=data.candidates[0].id;report.status='mapped';save();
 }
 await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Open readings',exact:true}).click();
 const reviewResponse=page.waitForResponse(r=>r.url().includes(`/candidates/${report.candidate_id}/review?`));await page.getByRole('button',{name:`Review source row ${row.row_index+1}`,exact:true}).click();const review=await(await reviewResponse).json();
 if(review.status!=='pending'||review.reading!==null||!JSON.stringify(review.original).includes('500.00'))throw Error('Original OCR reading not preserved pending');
 const region=page.getByRole('region',{name:'Original document beside review',exact:true});await region.getByRole('button',{name:`Source column ${cell.column_index+1}: amount`,exact:true}).click();await region.getByAltText('Page 51 of the source document',{exact:true}).waitFor();await region.scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-ocr-pending-review.png'});
 if(writes!==(readOnly?0:1))throw Error('Unexpected write count');report.status='verified_pending';report.latest_run_financial_writes=writes;report.ledger_admission=false;report.originals_preserved=true;save();console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
