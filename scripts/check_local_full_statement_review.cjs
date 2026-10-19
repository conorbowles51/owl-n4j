// First complete printed statement acceptance: payment, purchase and interest, PDF pages 1–3. Other statements in the 108-page file remain outside this test.
// Writes only into the isolated case created by check_local_pdf_intake_ui.cjs.
const path=require('path'),fs=require('fs');const root=path.resolve(__dirname,'..');const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
const output=path.join(root,'data/local-runtime/full-statement-review-check.json');
const resume=process.argv[2]==='--resume-interest';
(async()=>{if(fs.existsSync(output)&&!resume)throw Error('Review record exists; inspect before retrying any write');const intake=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/full-statement-pdf-intake-check.json')));if(intake.case_id!=='e8ecc646-7b29-49d6-b64d-7086a9a14ad4')throw Error('Unexpected acceptance case');
 const report=resume?JSON.parse(fs.readFileSync(output)):{case_id:intake.case_id,status:'started'};if(resume&&(!report.interest_mapping_id||report.interest_review_saved||report.status!=='mapped'))throw Error('Not at the pending interest checkpoint');const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(30000);await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 if(!resume){
 await page.goto(`http://127.0.0.1:55174/cases/${intake.case_id}/financial`);await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();await page.getByRole('button',{name:`${intake.filename} · page 3`,exact:true}).click();
 for(const [col,meaning] of [[1,'transaction_date'],[2,'description'],[3,'amount']])await page.getByLabel(`Column ${col} meaning`,{exact:true}).selectOption(meaning);
 for(const n of [10,13])await page.getByLabel(`Select source row ${n}`,{exact:true}).check();
 const mappingResponse=page.waitForResponse(r=>r.url().includes('/candidate-mappings?')&&r.request().method()==='POST');save();await page.getByRole('button',{name:'Save selected rows for review',exact:true}).click();const mapped=await mappingResponse;const mapping=await mapped.json();if(!mapped.ok()||mapping.candidates.length!==2)throw Error('Unexpected mapping outcome');report.mapping_id=mapping.id;report.candidate_ids=mapping.candidates.map(c=>c.id);report.status='mapped';save();
 for(const [i,n,amount,date,description,direction] of [[0,10,'180.00','2020-05-30','PAYMENT','credit'],[1,13,'61.62','2020-05-29','TSP*COPPER WEAR MA804-4515000PA','debit']]){
  await page.getByRole('button',{name:`Review source row ${n}`,exact:true}).click();await page.getByLabel('Currency',{exact:true}).fill('USD');
  if(i===0){await page.getByRole('button',{name:'Set up a provisional account',exact:true}).click();await page.getByLabel('Provisional account label',{exact:true}).fill('LOCAL SAMPLE — Capital One statement page 3');await page.getByLabel('Reason for provisional account',{exact:true}).fill('Isolated two-row acceptance sample. Source page 3 is a US credit-card statement; this provisional account does not establish wider account identity.');const pending=page.waitForResponse(r=>r.url().includes('/provisional-account?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Create provisional account',exact:true}).click();const response=await pending;const account=await response.json();if(!response.ok())throw Error('Account setup failed');report.account_id=account.account.id;save();}
  else await page.getByLabel('Account',{exact:true}).selectOption(report.account_id);
  await page.getByLabel('Reviewed amount',{exact:true}).fill(amount);await page.getByLabel('Direction',{exact:true}).selectOption(direction);await page.getByLabel('Transaction date',{exact:true}).fill(date);await page.getByLabel('Description',{exact:true}).fill(description);await page.getByLabel('Reason for decision',{exact:true}).fill('Isolated acceptance: visually checked original PDF page 3 payment or purchase row and amount. Year 2020 from the same statement header; USD context from US issuer and printed dollar amounts. Payment is a credit shown as a negative amount; purchase is a debit. Printed totals and interest sections were not selected. Two selected rows only; no complete-statement verification.');
  const source=page.getByRole('region',{name:'Original document beside review',exact:true});await source.getByRole('button',{name:'Source column 3: amount',exact:true}).click();const image=source.getByAltText('Page 3 of the source document',{exact:true});await image.waitFor();await image.evaluate(img=>img.decode());await source.evaluate(el=>el.scrollIntoView({block:'start'}));if(i===0)await page.screenshot({path:'/tmp/loupe-full-statement-row-review.png'});
  const pending=page.waitForResponse(r=>r.url().includes('/review?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Record resolved reading',exact:true}).click();const response=await pending;const review=await response.json();if(!response.ok()||review.status!=='resolved'||review.reading.amount_minor!==(i===0?'18000':'6162'))throw Error('Review failed '+JSON.stringify(review));report['review_'+i]=review.candidate_id;save();await page.getByRole('button',{name:'Close review',exact:true}).click();
 }
 // A different source layout for the undated interest row: make a separate UI-selected batch.
 await page.goto(`http://127.0.0.1:55174/cases/${intake.case_id}/financial`);
 await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();
 await page.getByRole('button',{name:'Choose PDF rows',exact:true}).click();
 await page.getByRole('button',{name:`${intake.filename} · page 3`,exact:true}).click();
 for(const [col,meaning] of [[1,'description'],[2,'amount']])await page.getByLabel(`Column ${col} meaning`,{exact:true}).selectOption(meaning);
 await page.getByLabel('Select source row 22',{exact:true}).check();
 const interestSave=page.waitForResponse(r=>r.url().includes('/candidate-mappings?')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Save selected rows for review',exact:true}).click();
 const interestResponse=await interestSave;const interest=await interestResponse.json();if(!interestResponse.ok()||interest.candidates.length!==1)throw Error('Interest selection failed');
 report.interest_mapping_id=interest.id;report.interest_candidate_id=interest.candidates[0].id;save();
 await page.getByRole('button',{name:'Review source row 22',exact:true}).click();
 await page.getByLabel('Currency',{exact:true}).fill('USD');await page.getByLabel('Account',{exact:true}).selectOption(report.account_id);
 await page.getByLabel('Reviewed amount',{exact:true}).fill('56.16');await page.getByLabel('Direction',{exact:true}).selectOption('debit');
 }else{
 await page.goto(`http://127.0.0.1:55174/cases/${intake.case_id}/financial`);
 await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();
 await page.getByRole('listitem').filter({hasText:'1 possible transactions'}).getByRole('button',{name:'Open readings',exact:true}).click();
 await page.getByRole('button',{name:'Review source row 22',exact:true}).click();
 await page.getByLabel('Currency',{exact:true}).fill('USD');await page.getByLabel('Account',{exact:true}).selectOption(report.account_id);
 await page.getByLabel('Reviewed amount',{exact:true}).fill('56.16');await page.getByLabel('Direction',{exact:true}).selectOption('debit');
 }
 await page.getByLabel('Statement end date (ordering only)',{exact:true}).fill('2020-06-11');
 await page.getByLabel('Description',{exact:true}).fill('Interest Charge on Purchases');
 await page.getByLabel('Reason for decision',{exact:true}).fill('Source page 3: interest charge on purchases $56.16 has no row date. Keep transaction, booking and value dates unknown. Use printed statement end June 11 2020 for ordering only; bind to page 1 printed period before finalization. Total-interest and APR rows repeat this charge and are not additional postings.');
 const interestReview=page.waitForResponse(r=>r.url().includes('/review?')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Record resolved reading',exact:true}).click();
 const interestReviewed=await interestReview;const interestState=await interestReviewed.json();
 if(!interestReviewed.ok()||interestState.reading.statement_end_date!=='2020-06-11'||interestState.reading.transaction_date!==null)throw Error('Undated interest review failed');
 report.interest_review_saved=true;save();await page.getByRole('button',{name:'Close review',exact:true}).click();
 await page.getByRole('button',{name:'Show document progress',exact:true}).click();
 await page.getByRole('region',{name:'Document review overview',exact:true}).getByText(/0 awaiting review · 3 resolved · 0 rejected/).first().waitFor();
 await page.getByRole('button',{name:'Preview finalization',exact:true}).click();
 if(!await page.getByRole('button',{name:'Finalize selected rows',exact:true}).isDisabled())throw Error('Missing statement control was not held');
 await page.getByRole('button',{name:'Add printed statement controls',exact:true}).click();
 await page.getByLabel('Statement account',{exact:true}).selectOption(`${report.account_id}:USD`);
 for(const n of [1,2,3])await page.getByLabel(`Assign reviewed row ${n} to statement`,{exact:true}).check();
 for(const [label,value] of [['Printed statement start','2020-05-12'],['Printed statement end','2020-06-11'],['Printed opening balance','6700.18'],['Printed closing balance','6637.96']])await page.getByLabel(label,{exact:true}).fill(value);
 await page.getByLabel('Printed balance convention',{exact:true}).selectOption('liability_owed');
 for(const [label,row,col] of [['statement start',3,1],['statement end',3,1],['opening balance',5,4],['closing balance',18,2]]){
  await page.getByRole('button',{name:`Choose source for ${label}`,exact:true}).click();
  const picker=page.getByRole('region',{name:`Choose source for ${label}`,exact:true});
  await picker.getByRole('button',{name:`Control row ${row}, column ${col}`,exact:true}).click();
  await picker.getByRole('button',{name:'Use this control cell',exact:true}).click();
 }
 await page.getByLabel('Reason for statement control readings',{exact:true}).fill('Visually checked original PDF page 1: May 12–June 11 2020, previous balance $6,700.18, new balance $6,637.96. Credit-card balances owed. The first printed statement contains payment $180.00, purchase $61.62 and purchase interest $56.16. Zero fees and zero cash-advance/other interest; summary, year-to-date and APR figures are not extra postings. Other statements in this PDF remain unreviewed. Unknown interest transaction date retained with statement-end ordering.');
 await page.screenshot({path:'/tmp/loupe-full-statement-editor.png',fullPage:true});
 await page.getByRole('button',{name:'Add statement to preview',exact:true}).click();
 const scopedPreview=page.waitForResponse(r=>r.url().includes('/finalization-preview?')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Preview finalization',exact:true}).click();
 const scoped=await scopedPreview;report.scoped_preview=await scoped.json();save();if(!scoped.ok()||report.scoped_preview.statement_scopes.length!==1)throw Error('Bound preview failed');
 await page.getByRole('checkbox',{name:/These are documentary/}).check();await page.getByRole('checkbox',{name:/I accept incomplete/}).check();await page.getByLabel('Reason for finalization').fill('First printed statement, PDF pages 1–3: payment, purchase and interest reviewed with printed opening/closing controls. Other statements remain outside coverage; retain P3. No invented interest transaction date.');
 const finalized=page.waitForResponse(r=>r.url().includes('/finalize?')&&r.request().method()==='POST');await page.getByRole('button',{name:'Finalize selected rows',exact:true}).click();const response=await finalized;report.finalization=await response.json();save();if(!response.ok())throw Error('Finalization failed');await page.getByText(/Finalized 3 transactions/).waitFor();report.status='finalized';save();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download ledger snapshot',exact:true}).click();await(await download).saveAs(path.join(root,'data/local-runtime/full-statement-export.zip'));report.export_downloaded=true;save();
 await page.getByRole('tab',{name:'Statements',exact:true}).click();
 const checked=page.waitForResponse(r=>r.url().includes('/statement-checks?'));
 await page.getByRole('button',{name:'Check statement balances',exact:true}).click();
 const checkResponse=await checked;report.statement_checks=await checkResponse.json();save();
 if(!checkResponse.ok()||report.statement_checks.items.length!==1||report.statement_checks.items[0].status!=='balanced')throw Error('Expected one balanced statement');
 await page.getByRole('region',{name:'Statement balance checks',exact:true}).getByText(/Checked at/).waitFor();
 await page.screenshot({path:'/tmp/loupe-full-statement-result.png',fullPage:true});
 report.status='verified';save();console.log(JSON.stringify(report));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
