const { chromium, firefox, webkit } = require(process.argv[2] + '/node_modules/playwright');
const fs = require('fs');
const files = fs.readdirSync(process.argv[3]).filter(f => !f.endsWith('.html')).sort();
(async () => {
  const results = {};
  for (const [label, type, opts] of [['chromium (Chrome for Testing 1208)', chromium, {channel: 'chromium'}], ['firefox 1509', firefox, {}], ['webkit 2248', webkit, {}]]) {
    let browser;
    try { browser = await type.launch({ headless: true, ...opts, args: type === chromium ? ['--autoplay-policy=no-user-gesture-required'] : [] }); }
    catch (e) { results[label] = { launchError: String(e).split('\n')[0] }; continue; }
    const page = await browser.newPage();
    await page.goto(process.argv[4]);
    results[label] = { version: browser.version(), files: {} };
    for (const f of files) {
      try { results[label].files[f] = await page.evaluate(n => window.probe(n), f); }
      catch (e) { results[label].files[f] = { probeError: String(e).split('\n')[0] }; }
    }
    await browser.close();
  }
  fs.writeFileSync(process.argv[5], JSON.stringify(results, null, 1));
})();
