import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const OUTPUT_DIR = 'docs/guide-assets';
mkdirSync(OUTPUT_DIR, { recursive: true });

const BASE_URL = 'http://localhost:5173';

// JWT token for neil.byrne@gmail.com (generated with default secret key)
const AUTH_TOKEN = process.env.AUTH_TOKEN || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJuZWlsLmJ5cm5lQGdtYWlsLmNvbSIsImV4cCI6MTc3MjA1NzA5MH0.hKvOr2Gpd6dIpPZ6Or3oM8gddXhFlJCCOBHCXCoLIL8';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1536, height: 900 },
  });

  const page = await context.newPage();

  // Navigate to app first to set the origin
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Inject auth token into localStorage
  await page.evaluate((token) => {
    localStorage.setItem('authToken', token);
  }, AUTH_TOKEN);

  const waitForStable = async (ms = 2000) => {
    await page.waitForTimeout(ms);
  };

  // ====== 1. Case Management Page ======
  console.log('1. Navigating to case management...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await waitForStable(3000);

  // Check if we're still on login
  const isLogin = await page.locator('text=Sign In').first().isVisible().catch(() => false);
  if (isLogin) {
    console.error('   Still on login page! Trying cookie auth...');
    await context.addCookies([{
      name: 'access_token',
      value: AUTH_TOKEN,
      domain: 'localhost',
      path: '/',
    }]);
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await waitForStable(3000);
  }

  console.log('   Taking case management screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/case-management.png` });

  // ====== 2. Click on Operation Silver Bridge to see case detail ======
  console.log('2. Opening Operation Silver Bridge...');
  const caseLink = page.locator('text=Operation Silver Bridge');
  await caseLink.waitFor({ timeout: 5000 }).catch(() => {});
  if (await caseLink.isVisible()) {
    await caseLink.click();
    await waitForStable(3000);
    console.log('   Taking case detail/evidence screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/case-detail-evidence.png` });

    // ====== 3. Evidence Processing View ======
    console.log('3. Looking for Evidence Processing button...');
    const evidenceBtn = page.locator('button:has-text("Evidence"), a:has-text("Evidence Processing"), button:has-text("Process")').first();
    if (await evidenceBtn.isVisible().catch(() => false)) {
      await evidenceBtn.click();
      await waitForStable(4000);
      console.log('   Taking evidence processing screenshot...');
      await page.screenshot({ path: `${OUTPUT_DIR}/evidence-processing.png` });

      // Go back to case management
      const backBtn = page.locator('button:has-text("Back"), button:has-text("Cases"), [aria-label="Back"]').first();
      if (await backBtn.isVisible().catch(() => false)) {
        await backBtn.click();
        await waitForStable(2000);
      }
    } else {
      console.log('   Evidence Processing button not found, skipping...');
    }

    // ====== 4. Open Workspace ======
    console.log('4. Opening workspace...');
    // May need to re-select the case
    if (!(await page.locator('text=Operation Silver Bridge').isVisible().catch(() => false))) {
      await page.goto(BASE_URL, { waitUntil: 'networkidle' });
      await waitForStable(2000);
    }
    const caseLink2 = page.locator('text=Operation Silver Bridge');
    if (await caseLink2.isVisible().catch(() => false)) {
      await caseLink2.click();
      await waitForStable(2000);
    }

    const openCase = page.locator('button:has-text("Open Case"), button:has-text("Open Workspace"), button:has-text("Open in Workspace")').first();
    if (await openCase.isVisible().catch(() => false)) {
      await openCase.click();
      await waitForStable(5000);
    }
  }

  // ====== 5. Knowledge Graph ======
  console.log('5. Taking knowledge graph screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/knowledge-graph.png` });

  // ====== 6. Workspace Sidebar (expand sections) ======
  console.log('6. Taking workspace sidebar screenshot...');
  // Try to show left sidebar with sections visible
  // The sidebar should already be visible with Case Overview, Theories, etc.
  await page.screenshot({ path: `${OUTPUT_DIR}/workspace-sidebar.png` });

  // ====== 7. Financial Dashboard ======
  console.log('7. Navigating to Financial view...');
  await page.locator('text=Financial').first().click().catch(() => {});
  await waitForStable(3000);

  // Click "None" on Category row to show all transactions
  const catNone = page.locator('text=None').nth(1);
  if (await catNone.isVisible().catch(() => false)) {
    await catNone.click();
    await waitForStable(2000);
  }

  // Collapse filters
  const filtersToggle = page.locator('text=Filters').first();
  if (await filtersToggle.isVisible().catch(() => false)) {
    await filtersToggle.click();
    await waitForStable(1000);
  }

  console.log('   Taking financial dashboard screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/financial-dashboard.png` });

  // ====== 8. Map View ======
  console.log('8. Navigating to Map view...');
  await page.locator('text=Map').first().click().catch(() => {});
  await waitForStable(3000);
  console.log('   Taking map view screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/map-view.png` });

  // ====== 9. Timeline View ======
  console.log('9. Navigating to Timeline view...');
  await page.locator('text=Timeline').first().click().catch(() => {});
  await waitForStable(3000);

  // Scroll to 2021+ data area
  await page.evaluate(() => {
    const scrollables = document.querySelectorAll('[class*="overflow-y-auto"], [class*="overflow-auto"], [style*="overflow"]');
    scrollables.forEach(el => {
      if (el.scrollHeight > el.clientHeight + 100) {
        el.scrollTop = el.scrollHeight * 0.65;
      }
    });
    const main = document.querySelector('main') || document.querySelector('[class*="timeline"]') || document.querySelector('[class*="content"]');
    if (main && main.scrollHeight > main.clientHeight) {
      main.scrollTop = main.scrollHeight * 0.65;
    }
  });
  await waitForStable(1000);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.6));
  await waitForStable(1000);

  console.log('   Taking timeline screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/timeline-view.png` });

  // ====== 10. Table View ======
  console.log('10. Navigating to Table view...');
  await page.locator('text=Table').first().click().catch(() => {});
  await waitForStable(3000);
  console.log('   Taking table view screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/table-view.png` });

  // ====== 11. Entity Detail Panel (click Elena Petrova) ======
  console.log('11. Clicking on Elena Petrova for entity detail...');
  const elenaRow = page.locator('td:has-text("Elena Petrova")').first();
  if (await elenaRow.isVisible().catch(() => false)) {
    await elenaRow.click();
    await waitForStable(2000);
    console.log('   Taking entity detail panel screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/entity-detail-panel.png` });

    // ====== 12. AI Chat Panel ======
    console.log('12. Opening AI chat panel...');
    const headerBtns = await page.locator('button svg').all();
    for (const svg of headerBtns) {
      const box = await svg.boundingBox().catch(() => null);
      if (box && box.x > 1400 && box.y < 50) {
        await svg.click();
        await waitForStable(1000);
        const aiPanel = page.locator('text=AI Assistant');
        if (await aiPanel.isVisible().catch(() => false)) {
          break;
        }
      }
    }
    await waitForStable(2000);
    console.log('   Taking AI chat panel screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/ai-chat-panel.png` });
  }

  // ====== 13. AI Insights Panel (Solaris Property Group) ======
  console.log('13. Looking for Solaris Property Group for AI Insights...');
  const searchInput = page.locator('input[placeholder*="Filter"]').first();
  if (await searchInput.isVisible().catch(() => false)) {
    await searchInput.fill('Solaris Property');
    await waitForStable(2000);
  }
  const solarisRow = page.locator('td:has-text("Solaris Property Group")').first();
  if (await solarisRow.isVisible().catch(() => false)) {
    await solarisRow.click();
    await waitForStable(2000);

    const verifiedFacts = page.locator('text=VERIFIED FACTS').first();
    if (await verifiedFacts.isVisible().catch(() => false)) {
      await verifiedFacts.click();
      await waitForStable(1000);
    }

    await page.evaluate(() => {
      const panels = document.querySelectorAll('[class*="overflow-y-auto"], [class*="overflow-auto"]');
      panels.forEach(p => {
        if (p.scrollHeight > p.clientHeight && p.getBoundingClientRect().right > 1200) {
          p.scrollTop += 400;
        }
      });
    });
    await waitForStable(1000);
    console.log('   Taking AI insights panel screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/ai-insights-panel.png` });
  }

  // ====== 14. Switch back to Graph view for graph screenshot ======
  console.log('14. Switching back to Graph view...');
  // Clear filter first
  if (await searchInput.isVisible().catch(() => false)) {
    await searchInput.fill('');
    await waitForStable(1000);
  }
  await page.locator('text=Graph').first().click().catch(() => {});
  await waitForStable(3000);

  // Close any side panels to show clean graph
  // Press Escape to close panels
  await page.keyboard.press('Escape');
  await waitForStable(1000);
  console.log('   Taking clean graph view screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/knowledge-graph.png` });

  console.log('\nAll workflow screenshots taken!');
  console.log('Screenshots saved to:', OUTPUT_DIR);
  await browser.close();
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
