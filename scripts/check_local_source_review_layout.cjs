// Read-only inspection of the existing synthetic finalized PDF review.
const path=require('path'),fs=require('fs');const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(20000);
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto('http://127.0.0.1:55174/cases/5adf884c-aede-4a8d-923e-c3f240d2f708/financial');await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Open readings',exact:true}).first().click();await page.getByRole('button',{name:'Review source row 1',exact:true}).click();
 const source=page.getByRole('region',{name:'Original document beside review',exact:true});const image=source.getByAltText('Page 1 of the source document',{exact:true});await image.waitFor();if(!await image.evaluate(img=>img.complete&&img.naturalWidth>0))throw Error('No rendered page');
 await source.getByRole('button',{name:'Source column 2: amount',exact:true}).click();await source.getByText('1234',{exact:false}).waitFor();
 await image.waitFor();await image.evaluate(img=>img.decode());
 await source.evaluate(el=>el.scrollIntoView({block:"start"}));const left=await source.boundingBox(),right=await page.getByLabel('Reviewed amount',{exact:true}).boundingBox();if(right.x<=left.x+left.width)throw Error('Review is not beside source');
 await page.screenshot({path:'/tmp/loupe-neilbyrne-source-review-desktop.png'});
 await page.setViewportSize({width:760,height:1000});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Narrow layout overflows');
 fs.writeFileSync(path.join(root,'data/local-runtime/source-review-layout-check.json'),JSON.stringify({desktop_side_by_side:true,source_image:true,column_switch:true,narrow_no_overflow:true,read_only:true},null,2));console.log('Source review layout passed');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
