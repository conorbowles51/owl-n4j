// Read-only browser check: block every financial mutation, leave source fixtures untouched.
const fs=require('fs'),path=require('path');
const {chromium}=require(path.resolve(__dirname,'../frontend_v2/node_modules/playwright'));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(30000);let blocked=0;
  await page.route('**/api/financial/**',async route=>{if(!['GET','HEAD'].includes(route.request().method())){blocked++;await route.abort()}else await route.continue()});
  await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
  await page.goto('http://127.0.0.1:55174/cases/e8ecc646-7b29-49d6-b64d-7086a9a14ad4/financial');
  await page.getByRole('tab',{name:'Transactions',exact:true}).click();
  await page.getByRole('button',{name:'View source',exact:true}).first().click();
  await page.getByRole('button',{name:'Source custody records',exact:true}).click();
  await page.getByText('No custody reports recorded. Earlier custody is unknown.',{exact:true}).waitFor();
  await page.getByLabel('Received by',{exact:true}).fill('UNSAVED synthetic browser check');
  await page.getByRole('button',{name:'Choose a certification file from this case',exact:true}).click();
  await page.getByText('Loading case files…',{exact:true}).waitFor({state:'hidden'});
  await page.getByLabel('Received by',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-custody-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  if(await page.getByLabel('Received by',{exact:true}).inputValue()!=='UNSAVED synthetic browser check')throw Error('Custody form lost on resize');
  await page.getByLabel('Received by',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-custody-mobile.png'});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Custody view overflows viewport');
  if(blocked)throw Error('Unexpected financial mutation attempted');
  console.log(JSON.stringify({source_custody_loaded:true,unknown_history_explicit:true,case_certification_picker_loaded:true,narrow_form_preserved:true,financial_writes:0}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
