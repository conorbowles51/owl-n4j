// Uses only the synthetic case produced by check_local_finalization_ui.cjs.
const path = require('path'), fs = require('fs');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'frontend_v2/node_modules/playwright'));
(async () => {
  const fixture = JSON.parse(fs.readFileSync(path.join(root, 'data/local-runtime/finalization-ui-check.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
    page.setDefaultTimeout(20000);
    await page.goto('http://127.0.0.1:55174/login');
    await page.getByPlaceholder('Enter your username').fill('loupe-local@example.com');
    await page.getByPlaceholder('Enter your password').fill('Loupe-local-test-2026');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL(url => !url.pathname.includes('login'));
    await page.goto(`http://127.0.0.1:55174/cases/${fixture.case_id}/financial`);
    await page.getByRole('tab', { name: 'Ledger', exact: true }).click();
    await page.getByRole('button', { name: 'Open PDF readings', exact: true }).click();
    await page.getByRole('button', { name: 'Open readings', exact: true }).first().click();
    const reviewResponse = page.waitForResponse(r => r.url().includes('/review?') && r.request().method() === 'GET');
    await page.getByRole('button', { name: /^Review source row/ }).first().click();
    const response = await reviewResponse, review = await response.json();
    if (review.finalization_id !== fixture.finalization_id) throw new Error('Review does not identify its finalization');
    const headers = await response.request().allHeaders();
    await page.getByText(/Finalized reading. Original values/).waitFor();
    if (!await page.getByLabel('Reviewed amount', { exact: true }).isDisabled()) throw new Error('Finalized review is editable');
    for (const name of ['Record resolved reading', 'Reject reading', 'Reopen for review', 'Create provisional account']) {
      if (await page.getByRole('button', { name, exact: true }).count()) throw new Error(`Finalized screen offers ${name}`);
    }
    await page.getByText(/Review history \(/).click();
    await page.getByRole('button', { name: 'Assess original amounts', exact: true }).click();
    await page.getByText(/Numeric reading:/).first().waitFor();
    await page.getByText(/Finalized reading. Original values/).scrollIntoViewIfNeeded();
    await page.screenshot({ path: '/tmp/loupe-neilbyrne-finalized-review-ui.png' });
    const denied = await page.request.post(`http://127.0.0.1:55174/api/financial/candidates/${review.candidate_id}/provisional-account?case_id=${fixture.case_id}`, {
      headers: { authorization: headers.authorization }, data: { expected_revision: review.review_revision, currency: 'GBP', label: 'Unused synthetic account', reason: 'Verify finalized protection' }
    });
    if (denied.status() !== 409) throw new Error(`Account setup was not refused: ${denied.status()} ${await denied.text()}`);
    await page.getByRole('button', { name: 'Close review', exact: true }).click();
    const original = fixture.transactions[0];
    const row = page.locator(`[data-row-key="${original.transaction_id}"]`);
    await row.getByRole('button', { name: 'Correct amount', exact: true }).click();
    await page.getByLabel('Proposed amount (GBP)', { exact: true }).fill('12.35');
    await page.getByRole('button', { name: 'Preview correction', exact: true }).click();
    await page.getByText('Document verification: p3 → p3. This applies to all rows in this source document.').waitFor();
    await page.getByLabel('Reason for correction', { exact: true }).fill('Synthetic correction after PDF finalization; preserve original source and incomplete coverage');
    const corrected = page.waitForResponse(r => r.url().includes('/correction?') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Record correction', exact: true }).click();
    const correctionResponse = await corrected, correction = await correctionResponse.json();
    if (correctionResponse.status() !== 200 || correction.proof_class !== 'p3') throw new Error(JSON.stringify(correction));
    await page.locator(`[data-row-key="${correction.replacement_id}"]`).waitFor();
    if (await row.count()) throw new Error('Superseded original remains in the current ledger');
    await page.getByRole('button', { name: 'Close correction', exact: true }).click();
    await page.getByRole('button', { name: 'Preview finalization', exact: true }).click();
    await page.getByText(/original reading has a later correction/).waitFor();
    await page.getByRole('button', { name: `View source: ${original.ref_id}`, exact: true }).click();
    await page.getByText('This is an original reading that has been replaced.').waitFor();
    await page.waitForFunction(() => Array.from(document.querySelectorAll('[role="dialog"] img')).some(img => img.complete && img.naturalWidth > 0));
    await page.screenshot({ path: '/tmp/loupe-neilbyrne-finalized-correction-source-ui.png' });
    fs.writeFileSync(path.join(root, 'data/local-runtime/finalized-review-ui-check.json'), JSON.stringify({ case_id: fixture.case_id, finalization_id: fixture.finalization_id, original, correction, readonly_review: 'passed', source_assessment: 'passed', sealed_account_refused: 'passed', receipt_and_original_source: 'passed' }, null, 2));
    console.log(JSON.stringify({ case_id: fixture.case_id, correction, result: 'passed' }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
