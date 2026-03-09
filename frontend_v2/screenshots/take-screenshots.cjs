const { chromium } = require('playwright');

const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzY3JlZW5zaG90QHRlbXAuY29tIiwiZXhwIjoxNzczMDkzNzI5fQ.oDCo_EINm7cSYFGFrjVB_JDS1U0--IFbD7NBLmlCxJA';
const BASE = 'http://localhost:5174';

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  // 1. Login page (before auth)
  await page.goto(`${BASE}/login`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/01-login.png' });
  console.log('1/10 Login page');

  // Set auth token to bypass login
  await page.evaluate((token) => {
    localStorage.setItem('authToken', token);
  }, TOKEN);

  // 2. Dashboard
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'screenshots/02-dashboard.png' });
  console.log('2/10 Dashboard');

  // 3. Cases list
  await page.goto(`${BASE}/cases`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/03-cases.png' });
  console.log('3/10 Cases list');

  // 4. Settings page
  await page.goto(`${BASE}/settings`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/04-settings.png' });
  console.log('4/10 Settings');

  // 5. Admin dashboard
  await page.goto(`${BASE}/admin`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/05-admin-dashboard.png' });
  console.log('5/10 Admin dashboard');

  // 6. Admin users
  await page.goto(`${BASE}/admin/users`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/06-admin-users.png' });
  console.log('6/10 Admin users');

  // 7. Admin profiles
  await page.goto(`${BASE}/admin/profiles`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/07-admin-profiles.png' });
  console.log('7/10 Admin profiles');

  // 8. Admin logs
  await page.goto(`${BASE}/admin/logs`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/08-admin-logs.png' });
  console.log('8/10 Admin logs');

  // 9. Admin tasks
  await page.goto(`${BASE}/admin/tasks`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/09-admin-tasks.png' });
  console.log('9/10 Admin tasks');

  // 10. Admin usage
  await page.goto(`${BASE}/admin/usage`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'screenshots/10-admin-usage.png' });
  console.log('10/10 Admin usage');

  await browser.close();
  console.log('\nDone! Screenshots saved to frontend_v2/screenshots/');
}

main().catch(console.error);
