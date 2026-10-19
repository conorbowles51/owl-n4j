// Read-only acceptance of current checks, coverage timeline and registered source navigation.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'frontend_v2/node_modules/playwright'));
(async()=>{
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1600,height:1100}});let writes=0;
    await page.route('**/api/financial/**',async route=>{
      if(!['GET','HEAD'].includes(route.request().method())){writes++;await route.abort()}else await route.continue();
    });
    await page.goto('http://127.0.0.1:55174/login');await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>!u.pathname.includes('login'));
    const headers={Authorization:`Bearer ${await page.evaluate(()=>localStorage.getItem('authToken'))}`};
    const read=async(url)=>{const response=await page.request.get(`http://127.0.0.1:58002/api/financial/${url}`,{headers});if(!response.ok())throw Error(`${response.status()} ${await response.text()}`);return response.json()};
    const report={cases:[],financial_writes:0};
    for(const caseId of ['e0da5581-a1ac-4db5-a3a9-e17021fb807a','4d897cb5-b9e4-4df7-9a21-b1ba4b8bf5d7','5675421f-0860-4048-abe1-902241a1feec']){
      const before=await read(`reconciliation?case_id=${caseId}`);
      await page.goto(`http://127.0.0.1:55174/cases/${caseId}/financial`);
      await page.getByRole('tab',{name:'Statements',exact:true}).click();
      const pending=page.waitForResponse(r=>r.url().includes('/statement-checks?'));
      await page.getByRole('button',{name:'Check statement balances',exact:true}).click();
      const response=await pending,checks=await response.json();if(!response.ok()||checks.case_id!==caseId||checks.applied!==false)throw Error('Invalid current checks');
      const panel=page.getByRole('region',{name:'Statement balance checks',exact:true});
      await panel.getByText(/Checked at/).waitFor();await panel.scrollIntoViewIfNeeded();
      await page.screenshot({path:`/tmp/loupe-neilbyrne-statement-check-${caseId}.png`});
      if(JSON.stringify(before)!==JSON.stringify(await read(`reconciliation?case_id=${caseId}`)))throw Error('Read changed stored reconciliation');
      if(caseId.startsWith('567542') && checks.items.length){
        const runningResponse=page.waitForResponse(r=>r.url().includes('/running-balances?'));
        await panel.getByRole('button',{name:'Check running balances',exact:true}).first().click();
        const running=await(await runningResponse).json();
        if(!running.comparison.available || running.applied!==false || running.comparison.interpretations.some(i=>'proposed' in i))throw Error('Unexpected current running-balance result');
        await panel.getByText('Assuming source row order',{exact:true}).waitFor();
        await panel.getByRole('region',{name:'Current statement running balances',exact:true}).first().scrollIntoViewIfNeeded();
        await page.screenshot({path:'/tmp/loupe-neilbyrne-current-running-balances.png'});
        report.running_balances=running.comparison;
        const citation=await read(`statement-periods/${checks.items[0].period_id}/source?case_id=${caseId}`);
        await panel.getByRole('button',{name:'Inspect statement source',exact:true}).first().click();
        await page.getByRole('button',{name:'Open statement file',exact:true}).waitFor();
        await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-source-dialog.png'});
        await page.getByRole('button',{name:'Open statement file',exact:true}).click();
        await page.getByText(citation.filename,{exact:true}).first().waitFor();
        report.source_navigation=true;
      }
      report.cases.push({case_id:caseId,periods:checks.items.length,statuses:checks.items.map(p=>p.status),stored_results_unchanged:true});
    }
    await page.goto('http://127.0.0.1:55174/cases/e0da5581-a1ac-4db5-a3a9-e17021fb807a/financial');
    await page.getByRole('tab',{name:'Statements',exact:true}).click();
    await page.getByRole('button',{name:'Check statement coverage',exact:true}).click();
    const timeline=page.getByRole('region',{name:'GBP statement timeline',exact:true}).first();await timeline.waitFor();await timeline.scrollIntoViewIfNeeded();
    await timeline.getByRole('button',{name:/Inspect statement/}).first().click();
    await timeline.getByRole('region',{name:'Selected statement period',exact:true}).waitFor();
    await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-timeline.png'});
    await page.setViewportSize({width:850,height:1100});await timeline.scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/loupe-neilbyrne-statement-timeline-narrow.png'});
    if(writes)throw Error('Unexpected financial write');report.financial_writes=writes;report.timeline_selection=true;
    fs.writeFileSync(path.join(root,'data/local-runtime/statement-workflow-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
