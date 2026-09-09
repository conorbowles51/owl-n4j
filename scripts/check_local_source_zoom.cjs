// Read-only inspection of the existing synthetic finalized PDF review.
const path=require('path'),fs=require('fs');const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});page.setDefaultTimeout(20000);
 await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
 await page.goto('http://127.0.0.1:55174/cases/c06c264c-a402-4895-a696-be634fe23629/financial');await page.getByRole('button',{name:'Open PDF readings',exact:true}).click();await page.getByRole('button',{name:'Open readings',exact:true}).first().click();await page.getByRole('button',{name:'Review source row 41',exact:true}).click();
 const source=page.getByRole('region',{name:'Original document beside review',exact:true});const image=source.getByAltText('Page 4 of the source document',{exact:true});await image.waitFor();if(!await image.evaluate(img=>img.complete&&img.naturalWidth>0))throw Error('No rendered page');
 await source.getByRole('button',{name:'Source column 4: amount',exact:true}).click();await source.getByText('14.00',{exact:false}).waitFor();
 await image.waitFor();await image.evaluate(img=>img.decode());
 const before=await image.boundingBox();for(let i=0;i<4;i++)await source.getByRole('button',{name:'Zoom source in',exact:true}).click();
 const after=await image.boundingBox();if(Math.abs(after.width/before.width-3)>0.03)throw Error('Unexpected source zoom');
 const box=await source.getByTestId('locator-highlight-box').boundingBox();const viewport=await source.getByRole('region',{name:'Scrollable source page',exact:true}).boundingBox();
 if(box.x+box.width<viewport.x||box.x>viewport.x+viewport.width||box.y+box.height<viewport.y||box.y>viewport.y+viewport.height)throw Error('Zoom lost highlighted value');
 await source.evaluate(el=>el.scrollIntoView({block:'start'}));await page.screenshot({path:'/tmp/loupe-neilbyrne-source-zoom.png'});
 await source.getByRole('button',{name:'Fit source width',exact:true}).click();await source.getByText('100%',{exact:true}).waitFor();
 fs.writeFileSync(path.join(root,'data/local-runtime/source-zoom-check.json'),JSON.stringify({zoom_300_percent:true,highlight_visible:true,fit_width:true,read_only:true},null,2));console.log('Source zoom passed');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
