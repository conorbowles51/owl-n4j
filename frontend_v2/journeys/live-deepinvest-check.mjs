#!/usr/bin/env node
// Deep investigation page check (lx-deepinvest G): signed in over plain http, the Agent page of the demo case at
// two widths: the Deep investigation switch, the cost sentence, and (while a deep run works) the checklist with its
// true counts. Read only. node journeys/live-deepinvest-check.mjs --shots <dir> --out <file.json>
import { mkdirSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d }
const shots = arg("shots"), out = arg("out")
if (!shots || !out) { console.error("usage: --shots <dir> --out <file.json>"); process.exit(2) }
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
    await page.goto(`${login.url}/cases/${CASES.demo}/agent`, { waitUntil: "domcontentloaded", timeout: 120_000 })
    const secure = await page.evaluate(() => window.isSecureContext)
    await page.waitForLoadState("networkidle", { timeout: 60_000 }).catch(() => {})
    await page.waitForTimeout(3000)
    const sw = page.getByLabel("Deep investigation")
    const hasSwitch = (await sw.count()) > 0
    if (hasSwitch) await sw.first().scrollIntoViewIfNeeded().catch(() => {})
    const line = await page.getByTestId("deep-checklist-line").first().textContent({ timeout: 2000 }).catch(() => null)
    const items = await page.getByTestId("deep-checklist").locator("li").count().catch(() => 0)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    await page.screenshot({ path: `${shots}/agent-${width}.png`, fullPage: false })
    result.widths.push({ width, secure, hasSwitch, checklistLine: line, checklistItems: items, horizontalOverflow: overflow, errors })
    console.log(width, JSON.stringify(result.widths.at(-1)))
    await page.close()
  }
} finally {
  writeFileSync(out, JSON.stringify(result, null, 1))
  await browser.close()
}
