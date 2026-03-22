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

  // Helper to wait
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
    console.error('Still on login page! Token may be invalid.');
    // Try setting cookie instead
    await context.addCookies([{
      name: 'access_token',
      value: AUTH_TOKEN,
      domain: 'localhost',
      path: '/',
    }]);
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await waitForStable(3000);
  }

  console.log('1. Taking case management screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/case-management.png` });

  // Click on "Operation Silver Bridge" case
  console.log('   Clicking Operation Silver Bridge...');
  const caseLink = page.locator('text=Operation Silver Bridge');
  await caseLink.waitFor({ timeout: 5000 }).catch(() => {});
  if (await caseLink.isVisible()) {
    await caseLink.click();
    await waitForStable(3000);

    // ====== 2. Case Detail with Evidence ======
    console.log('2. Taking case detail/evidence screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/case-detail-evidence.png` });

    // Click "Open Case" button
    const openCase = page.locator('button:has-text("Open Case")');
    if (await openCase.isVisible()) {
      await openCase.click();
      await waitForStable(5000);
    } else {
      // Try "Open Workspace" as alternative
      const openWorkspace = page.locator('button:has-text("Open Workspace")');
      if (await openWorkspace.isVisible()) {
        await openWorkspace.click();
        await waitForStable(5000);
      }
    }
  }

  // ====== 3. Knowledge Graph ======
  console.log('3. Taking knowledge graph screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/knowledge-graph.png` });

  // ====== 4. Financial Dashboard ======
  console.log('4. Navigating to Financial view...');
  const financialTab = page.locator('a:has-text("Financial"), button:has-text("Financial"), [role="tab"]:has-text("Financial")').first();
  // Try clicking Financial in the nav bar
  await page.locator('text=Financial').first().click().catch(() => {});
  await waitForStable(3000);

  // Click "None" on Category row to deselect all categories (shows all transactions)
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

  console.log('4. Taking financial dashboard screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/financial-dashboard.png` });

  // ====== 5. Map View ======
  console.log('5. Navigating to Map view...');
  await page.locator('text=Map').first().click().catch(() => {});
  await waitForStable(3000);
  console.log('5. Taking map view screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/map-view.png` });

  // ====== 6. Timeline View ======
  console.log('6. Navigating to Timeline view...');
  await page.locator('text=Timeline').first().click().catch(() => {});
  await waitForStable(3000);

  // Scroll down timeline to where there's data (2021+)
  // Use JavaScript to scroll the timeline container
  await page.evaluate(() => {
    const scrollables = document.querySelectorAll('[class*="overflow-y-auto"], [class*="overflow-auto"], [style*="overflow"]');
    scrollables.forEach(el => {
      if (el.scrollHeight > el.clientHeight + 100) {
        // Scroll 70% of the way down to reach 2021+ data
        el.scrollTop = el.scrollHeight * 0.65;
      }
    });
    // Also try the main content area
    const main = document.querySelector('main') || document.querySelector('[class*="timeline"]') || document.querySelector('[class*="content"]');
    if (main && main.scrollHeight > main.clientHeight) {
      main.scrollTop = main.scrollHeight * 0.65;
    }
  });
  await waitForStable(1000);
  // Also try window scroll as fallback
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.6));
  await waitForStable(1000);

  console.log('6. Taking timeline screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/timeline-view.png` });

  // ====== 7. Table View ======
  console.log('7. Navigating to Table view...');
  await page.locator('text=Table').first().click().catch(() => {});
  await waitForStable(3000);
  console.log('7. Taking table view screenshot...');
  await page.screenshot({ path: `${OUTPUT_DIR}/table-view.png` });

  // ====== 8. Entity Detail Panel (click Elena Petrova) ======
  console.log('8. Clicking on Elena Petrova for entity detail...');
  const elenaRow = page.locator('td:has-text("Elena Petrova")').first();
  if (await elenaRow.isVisible().catch(() => false)) {
    await elenaRow.click();
    await waitForStable(2000);
    console.log('8. Taking entity detail panel screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/entity-detail-panel.png` });

    // ====== 9. AI Chat Panel ======
    console.log('9. Opening AI chat panel...');
    // Find the chat button by looking for speech bubble icon buttons
    const buttons = await page.locator('header button, nav button').all();
    let chatClicked = false;
    for (const btn of buttons) {
      const box = await btn.boundingBox().catch(() => null);
      if (box && box.x > 1350 && box.y < 60 && box.width < 60 && box.height < 60) {
        // This is likely one of the header icons (refresh, chat, etc.)
        const ariaLabel = await btn.getAttribute('aria-label').catch(() => '');
        const title = await btn.getAttribute('title').catch(() => '');
        if ((ariaLabel + title).toLowerCase().includes('chat') ||
            (ariaLabel + title).toLowerCase().includes('assistant')) {
          await btn.click();
          chatClicked = true;
          break;
        }
      }
    }

    // If we couldn't find by aria-label, try clicking all header buttons until chat opens
    if (!chatClicked) {
      // Look for chat toggle by its position (second-to-last icon in header)
      const headerBtns = await page.locator('button svg').all();
      for (const svg of headerBtns) {
        const box = await svg.boundingBox().catch(() => null);
        if (box && box.x > 1400 && box.y < 50) {
          await svg.click();
          await waitForStable(1000);
          // Check if AI Assistant appeared
          const aiPanel = page.locator('text=AI Assistant');
          if (await aiPanel.isVisible().catch(() => false)) {
            chatClicked = true;
            break;
          }
        }
      }
    }

    await waitForStable(2000);
    console.log('9. Taking AI chat panel screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/ai-chat-panel.png` });
  }

  // ====== 10. AI Insights Panel ======
  console.log('10. Looking for entity with AI Insights (Solaris Property)...');
  // Use the table search/filter
  const searchInput = page.locator('input[placeholder*="Filter"]').first();
  if (await searchInput.isVisible().catch(() => false)) {
    await searchInput.fill('Solaris Property');
    await waitForStable(2000);
  }

  // Click Solaris Property Group row
  const solarisRow = page.locator('td:has-text("Solaris Property Group")').first();
  if (await solarisRow.isVisible().catch(() => false)) {
    await solarisRow.click();
    await waitForStable(2000);

    // Collapse Verified Facts section
    const verifiedFacts = page.locator('text=VERIFIED FACTS').first();
    if (await verifiedFacts.isVisible().catch(() => false)) {
      await verifiedFacts.click();
      await waitForStable(1000);
    }

    // Look for AI Insights section - scroll the side panel
    const aiInsights = page.locator('text=AI INSIGHTS').first();
    if (await aiInsights.isVisible().catch(() => false)) {
      await aiInsights.scrollIntoViewIfNeeded();
      await waitForStable(1000);
    }

    // Also try to scroll the side panel container
    await page.evaluate(() => {
      const panels = document.querySelectorAll('[class*="overflow-y-auto"], [class*="overflow-auto"]');
      panels.forEach(p => {
        if (p.scrollHeight > p.clientHeight && p.getBoundingClientRect().right > 1200) {
          p.scrollTop += 400;
        }
      });
    });
    await waitForStable(1000);

    console.log('10. Taking AI insights panel screenshot...');
    await page.screenshot({ path: `${OUTPUT_DIR}/ai-insights-panel.png` });
  } else {
    console.log('10. Solaris Property not found in table');
  }

  console.log('All screenshots taken!');
  await browser.close();
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
