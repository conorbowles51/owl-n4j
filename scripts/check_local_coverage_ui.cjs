const path=require('path'),fs=require('fs');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/local-runtime/coverage-check.json'),'utf8'));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1200}});page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:55174/login');
  await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
  await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(url=>!url.pathname.includes('login'));
  await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
  await page.getByRole('tab',{name:'Ledger',exact:true}).click();
  const pending=page.waitForResponse(r=>r.url().includes('/statement-coverage?'));
  await page.getByRole('button',{name:'Check statement coverage',exact:true}).click();
  const response=await pending,result=await response.json();
  if(response.status()!==200||result.applied!==false||result.items.length!==2)throw new Error(JSON.stringify(result));
  const gap=result.items.find(i=>i.account_id===fixture.gap_account_id).currencies[0];
  const enclosing=result.items.find(i=>i.account_id===fixture.enclosing_account_id).currencies[0];
  if(gap.uncovered_days!==28||enclosing.uncovered_days!==0||enclosing.covered_days!==90)throw new Error('Coverage union incorrect');
  await page.getByText(/Gap in eligible printed bounds: 2026-02-01 to 2026-02-28/).waitFor();
  await page.getByText(/GBP: 3 eligible periods; 90 calendar days/).waitFor();
  await page.getByRole('region',{name:'Statement coverage',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-coverage-ui.png'});
  fs.writeFileSync(path.join(root,'data/local-runtime/coverage-ui-check.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({case_id:fixture.case_id,gap_days:28,enclosing_gap_days:0,result:'passed'}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
