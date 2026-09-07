// Read-only check against the synthetic PDF fixture; does not change reviews or money.
const path=require('path'),fs=require('fs');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/candidate-check.json'),'utf8'));
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1200}});
  page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.waitForURL(url=>!url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab',{name:'Ledger',exact:true}).click();
  await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();
  await page.getByRole('button',{name:'Open readings',exact:true}).first().click();
  await page.getByRole('button',{name:/^Review source row/}).first().click();
  const completed=page.waitForResponse(r=>r.url().includes('/date-assessment?'));
  await page.getByRole('button',{name:'Assess original dates',exact:true}).click();
  const response=await completed,result=await response.json();
  if(response.status()!==200||result.applied!==false||result.date_cells[0]?.assessment.status!=='missing_year')throw new Error(JSON.stringify(result));
  if(result.date_cells.some(c=>c.assessment.proposals.some(p=>p.iso_date)))throw new Error('Missing year was invented');
  const section=page.getByRole('region',{name:'Original date assessment'});
  await section.getByText(/month 2, day 1; full year unresolved/).waitFor();
  await section.getByText(/month 1, day 2; full year unresolved/).waitFor();
  await section.locator('img').waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('[aria-label="Original date assessment"] img')).some(img=>img.complete&&img.naturalWidth>0));
  await section.scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-candidate-dates-ui.png'});
  console.log(JSON.stringify({case_id:fixture.case_id,candidate_id:result.candidate_id,result:'passed',missing_year:'preserved',source_image:'passed'}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
