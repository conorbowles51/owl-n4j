// Read-only conditional tracing of a separately seeded synthetic case.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/network-review-check.json')));
  if (fixture.status !== 'ready') throw Error('Synthetic fixture not ready');
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1100}});
    page.setDefaultTimeout(20000);
    page.on('framenavigated',f=>{if(f===page.mainFrame())console.log('Navigation',f.url())});
    page.on('console',m=>{if(m.type()==='error'||m.text().includes('vite'))console.log('Browser',m.text())});
    let writes = 0;
    await page.route('**/api/financial/**', async route => {
      if (!['GET','HEAD'].includes(route.request().method()) && !route.request().url().includes('/network-trace?')) { writes++; await route.abort(); }
      else await route.continue();
    });
    await page.goto('http://127.0.0.1:55174/login');
    await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
    await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await page.waitForURL(u=>!u.pathname.includes('login'));
    await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
    await page.getByRole('tab',{name:'Conditional tracing',exact:true}).click();
    await page.getByRole('button',{name:'Trace between accounts',exact:true}).click();
    await page.getByLabel('Trace from date',{exact:true}).fill('2026-01-01');
    await page.getByLabel('Trace through date',{exact:true}).fill('2026-01-31');
    await page.getByLabel('Cross-account population',{exact:true}).selectOption('working');
    const loaded = page.waitForResponse(r=>r.url().includes('/network-trace-inputs?'));
    await page.getByRole('button',{name:'Load cross-account inputs',exact:true}).click();
    const response = await loaded, scope = await response.json();
    if (!response.ok()) throw Error(JSON.stringify(scope));
    for (let i=1;i<=3;i++) {
      await page.getByLabel(`Opening amount account ${i}`,{exact:true}).fill('0.00');
      await page.getByLabel(`Opening basis account ${i}`,{exact:true}).fill('Explicit zero opening in this synthetic acceptance case.');
    }
    for (const pair of fixture.pairs) {
      const i=scope.candidates.findIndex(p=>p.debit_id===pair.debit_id&&p.credit_id===pair.credit_id);
      if(i<0) throw Error('Expected synthetic transfer absent');
      await page.getByLabel(`Trace transfer pair ${i+1}`,{exact:true}).check();
    }
    await page.getByLabel('Basis for selected transfers',{exact:true}).fill('Two explicitly seeded synthetic transfer pairs; this is not real bank evidence.');
    await page.getByLabel('Attributed deposit',{exact:true}).selectOption(fixture.root_id);
    await page.getByLabel('Claim label',{exact:true}).fill('Synthetic claim');
    await page.getByLabel('Attributed amount (GBP)',{exact:true}).fill('100.00');
    await page.getByLabel('Attribution basis',{exact:true}).fill('Synthetic root credit specified by the test fixture.');
    const ordered=scope.rows.filter(r=>r.currency==='GBP').sort((a,b)=>a.ordering_date.localeCompare(b.ordering_date)).map(r=>r.key);
    for(let target=0;target<fixture.ordered_ids.length;target++) {
      let at=ordered.indexOf(fixture.ordered_ids[target]);
      while(at>target) {
        await page.getByRole('button',{name:`Move network reading ${at+1} earlier`,exact:true}).click();
        [ordered[at-1],ordered[at]]=[ordered[at],ordered[at-1]];at--;
      }
    }
    await page.getByLabel('Basis for cross-account order',{exact:true}).fill('Seeded chronological movement order, with explicit same-day sender before receiver.');
    for(const method of ['first in first out','last in first out','pro rata']) await page.getByRole('checkbox',{name:method,exact:true}).check();
    const calculated=page.waitForResponse(r=>r.url().includes('/network-trace?'));
    await page.getByRole('button',{name:'Calculate cross-account scenario',exact:true}).click();
    const result=await calculated, envelope=await result.json();
    if(!result.ok()) throw Error(JSON.stringify(envelope));
    const report=JSON.parse(envelope.scenario_json);
    if(crypto.createHash('sha256').update(envelope.scenario_json).digest('hex')!==envelope.scenario_sha256) throw Error('Digest mismatch');
    const expected={first_in_first_out:'8000',last_in_first_out:'10000',pro_rata:'9000'};
    for(const [method,remaining] of Object.entries(expected)) {
      const value=report.results[method];
      if(value.claims['Synthetic claim'].reported_remaining_minor!==remaining||value.hops.length!==2) throw Error('Incorrect multi-hop result');
    }
    const results=page.getByRole('region',{name:'Cross-account tracing results',exact:true});
    await results.waitFor();console.log('Results rendered');
    const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download cross-account scenario',exact:true}).click();
    const output=path.join(root,'data/local-runtime/network-trace-scenario.json');await(await download).saveAs(output);
    console.log('Downloaded');await page.screenshot({path:'/tmp/loupe-network-trace-results.png'});
    if(fs.readFileSync(output,'utf8')!==envelope.scenario_json) throw Error('Download mismatch');
    await page.getByLabel('Opening amount account 1',{exact:true}).fill('1.00');
    if(await results.count()) throw Error('Stale results remain after assumption edit');
    if(writes) throw Error('Unexpected financial write');
    const verified={case_id:fixture.case_id,synthetic:true,accounts:3,postings:7,selected_hops:2,remaining_minor:expected,download_verified:true,stale_results_cleared:true,financial_writes:writes};
    fs.writeFileSync(path.join(root,'data/local-runtime/network-trace-ui-check.json'),JSON.stringify(verified,null,2));console.log(JSON.stringify(verified));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
