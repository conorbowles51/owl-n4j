// Deliberate two-row acceptance sample, visually checked on source PDF page 3.
// Writes only into the isolated case created by check_local_pdf_intake_ui.cjs.
const path=require('path'),fs=require('fs');const root=path.resolve(__dirname,'..');const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const output=path.join(root,'data/local-runtime/statement-controls-review-check.json');
(async()=>{if(fs.existsSync(output))throw Error('Review record exists; inspect before retrying any write');const intake=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/statement-controls-pdf-intake-check.json')));if(intake.case_id!=='c1453d2f-c2ff-47c6-a58a-1a9786803f44')throw Error('Unexpected acceptance case');
 const report={case_id:intake.case_id,status:'started'};const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto(`http://127.0.0.1:55174/cases/${intake.case_id}/financial`);await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();await page.getByRole('button',{name:`${intake.filename} · page 3`,exact:true}).click();
 for(const [col,meaning] of [[1,'transaction_date'],[2,'description'],[3,'amount']])await page.getByLabel(`Column ${col} meaning`,{exact:true}).selectOption(meaning);
 for(const n of [10,13])await page.getByLabel(`Select source row ${n}`,{exact:true}).check();
 const mappingResponse=page.waitForResponse(r=>r.url().includes('/candidate-mappings?')&&r.request().method()==='POST');save();await page.getByRole('button',{name:'Save selected rows for review',exact:true}).click();const mapped=await mappingResponse;const mapping=await mapped.json();if(!mapped.ok()||mapping.candidates.length!==2)throw Error('Unexpected mapping outcome');report.mapping_id=mapping.id;report.candidate_ids=mapping.candidates.map(c=>c.id);report.status='mapped';save();
 for(const [i,n,amount,date,description,direction] of [[0,10,'180.00','2020-05-30','PAYMENT','credit'],[1,13,'61.62','2020-05-29','TSP*COPPER WEAR MA804-4515000PA','debit']]){
  await page.getByRole('button',{name:`Review source row ${n}`,exact:true}).click();await page.getByLabel('Currency',{exact:true}).fill('USD');
  if(i===0){await page.getByRole('button',{name:'Set up a provisional account',exact:true}).click();await page.getByLabel('Provisional account label',{exact:true}).fill('LOCAL SAMPLE — Capital One statement page 3');await page.getByLabel('Reason for provisional account',{exact:true}).fill('Isolated two-row acceptance sample. Source page 3 is a US credit-card statement; this provisional account does not establish wider account identity.');const pending=page.waitForResponse(r=>r.url().includes('/provisional-account?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Create provisional account',exact:true}).click();const response=await pending;const account=await response.json();if(!response.ok())throw Error('Account setup failed');report.account_id=account.account.id;save();}
  else await page.getByLabel('Account',{exact:true}).selectOption(report.account_id);
  await page.getByLabel('Reviewed amount',{exact:true}).fill(amount);await page.getByLabel('Direction',{exact:true}).selectOption(direction);await page.getByLabel('Transaction date',{exact:true}).fill(date);await page.getByLabel('Description',{exact:true}).fill(description);await page.getByLabel('Reason for decision',{exact:true}).fill('Isolated acceptance: visually checked original PDF page 3 payment or purchase row and amount. Year 2020 from the same statement header; USD context from US issuer and printed dollar amounts. Payment is a credit shown as a negative amount; purchase is a debit. Printed totals and interest sections were not selected. Two selected rows only; no complete-statement verification.');
  const source=page.getByRole('region',{name:'Original document beside review',exact:true});await source.getByRole('button',{name:'Source column 3: amount',exact:true}).click();const image=source.getByAltText('Page 3 of the source document',{exact:true});await image.waitFor();await image.evaluate(img=>img.decode());await source.evaluate(el=>el.scrollIntoView({block:'start'}));if(i===0)await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-controls-row-review.png'});
  const pending=page.waitForResponse(r=>r.url().includes('/review?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Record resolved reading',exact:true}).click();const response=await pending;const review=await response.json();if(!response.ok()||review.status!=='resolved'||review.reading.amount_minor!==(i===0?'18000':'6162'))throw Error('Review failed '+JSON.stringify(review));report['review_'+i]=review.candidate_id;save();await page.getByRole('button',{name:'Close review',exact:true}).click();
 }
 await page.getByRole('button',{name:'Preview finalization',exact:true}).click();await page.getByRole('button',{name:'Add printed statement controls',exact:true}).click();
 await page.getByLabel('Statement account',{exact:true}).selectOption(`${report.account_id}:USD`);
 for(const n of [1,2])await page.getByLabel(`Assign reviewed row ${n} to statement`,{exact:true}).check();
 for(const [label,value] of [['Printed statement start','2020-05-12'],['Printed statement end','2020-06-11'],['Printed opening balance','6700.18'],['Printed closing balance','6637.96']])await page.getByLabel(label,{exact:true}).fill(value);
 await page.getByLabel('Printed balance convention',{exact:true}).selectOption('liability_owed');
 for(const [label,row,col] of [['statement start',3,1],['statement end',3,1],['opening balance',5,4],['closing balance',18,2]]){
  await page.getByRole('button',{name:`Choose source for ${label}`,exact:true}).click();
  const picker=page.getByRole('region',{name:`Choose source for ${label}`,exact:true});
  await picker.getByRole('button',{name:`Control row ${row}, column ${col}`,exact:true}).click();
  await picker.getByRole('button',{name:'Use this control cell',exact:true}).click();
 }
 await page.getByLabel('Reason for statement control readings',{exact:true}).fill('Visually checked original PDF page 1: May 12–June 11 2020, previous balance $6,700.18, new balance $6,637.96. Credit-card balances owed. This deliberate two-row sample omits $56.16 interest, so the current balance check must expose that difference; no full coverage claimed.');
 await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-controls-editor.png',fullPage:true});
 await page.getByRole('button',{name:'Add statement to preview',exact:true}).click();
 const scopedPreview=page.waitForResponse(r=>r.url().includes('/finalization-preview?')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Preview finalization',exact:true}).click();
 const scoped=await scopedPreview;report.scoped_preview=await scoped.json();save();if(!scoped.ok()||report.scoped_preview.statement_scopes.length!==1)throw Error('Bound preview failed');
 await page.getByRole('checkbox',{name:/These are documentary/}).check();await page.getByRole('checkbox',{name:/I accept incomplete/}).check();await page.getByLabel('Reason for finalization').fill('Isolated acceptance sample: only two visually reviewed payment and purchase rows from page 3. Incomplete extraction coverage is accepted for this test; retain P3 exclusion from verified totals.');
 const finalized=page.waitForResponse(r=>r.url().includes('/finalize?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Finalize selected rows',exact:true}).click();const response=await finalized;report.finalization=await response.json();save();if(!response.ok())throw Error('Finalization failed');await page.getByText(/Finalized 2 transactions/).waitFor();report.status='finalized';save();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();await(await download).saveAs(path.join(root,'data/local-runtime/statement-controls-sample-export.zip'));report.export_downloaded=true;save();
 await page.getByRole('tab',{name:'Statements',exact:true}).click();
 const checked=page.waitForResponse(r=>r.url().includes('/statement-checks?'));
 await page.getByRole('button',{name:'Check statement balances',exact:true}).click();
 const checkResponse=await checked;report.statement_checks=await checkResponse.json();save();
 if(!checkResponse.ok()||report.statement_checks.items.length!==1||report.statement_checks.items[0].status!=='unbalanced')throw Error('Expected one unbalanced statement');
 await page.getByRole('region',{name:'Statement balance checks',exact:true}).getByText(/Checked at/).waitFor();
 await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-controls-result.png',fullPage:true});
 report.status='verified';save();console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
