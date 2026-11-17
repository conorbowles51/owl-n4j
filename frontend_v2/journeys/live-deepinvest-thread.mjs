#!/usr/bin/env node
// Deep investigation answer check (lx-deepinvest G): signed in over plain http, open a stored thread at two widths,
// read the checklist and citation line, open five citations and report what opened. Read only.
// node journeys/live-deepinvest-thread.mjs --case <case id> --thread <thread id> --shots <dir> --out <file.json> [--label x]
import { mkdirSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { readLogin, signIn } from "./lib.mjs"

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d }
const [caseId, thread, shots, out] = ["case", "thread", "shots", "out"].map((n) => arg(n))
const label = arg("label", "thread")
if (!caseId || !thread || !shots || !out) { console.error("usage: --case --thread --shots --out [--label]"); process.exit(2) }
mkdirSync(shots, { recursive: true })
const login = readLogin()
const browser = await chromium.launch()
const result = { widths: [] }
try {
  const { context } = await signIn(browser, login)
  for (const width of [1500, 390]) {
    const page = await context.newPage()
    await page.setViewportSize({ width, height: 900 })
    const errors = []
    page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 200)))
    page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${new URL(r.url()).pathname}`) })
    await page.goto(`${login.url}/cases/${caseId}/agent?thread=${thread}`, { waitUntil: "domcontentloaded", timeout: 120_000 })
    await page.waitForLoadState("networkidle", { timeout: 60_000 }).catch(() => {})
    await page.waitForTimeout(4000)
    const secure = await page.evaluate(() => window.isSecureContext)
    const checkLine = await page.getByTestId("citation-check").first().textContent({ timeout: 3000 }).catch(() => null)
    const links = page.locator('a[href*="rec://"], button:has-text("phone record")')
    const found = await links.count()
    await page.screenshot({ path: `${shots}/${label}-${width}.png` })
    const opened = []
    for (let i = 0; i < Math.min(5, found); i++) {
      const before = page.url()
      await links.nth(i).scrollIntoViewIfNeeded().catch(() => {})
      await links.nth(i).click({ timeout: 5000 }).catch((e) => opened.push({ i, error: String(e.message).slice(0, 80) }))
      await page.waitForTimeout(2500)
      const dialog = await page.locator('[role="dialog"], [data-state="open"]').first().innerText({ timeout: 1500 }).catch(() => "")
      opened.push({ i, urlChanged: page.url() !== before, shown: dialog.slice(0, 120) })
      if (i === 0) await page.screenshot({ path: `${shots}/${label}-${width}-citation.png` })
      await page.keyboard.press("Escape").catch(() => {})
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    result.widths.push({ width, secure, checkLine: checkLine?.trim().slice(0, 200), citationLinks: found, opened, horizontalOverflow: overflow, errors })
    console.log(width, JSON.stringify(result.widths.at(-1)))
    await page.close()
  }
} finally {
  writeFileSync(out, JSON.stringify(result, null, 1))
  await browser.close()
}
