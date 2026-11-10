#!/usr/bin/env node
// Open each module's screen on the demo case as a person does (lx-demo H): signed in once with the jobs login over
// plain http, one page per module, a screenshot each, and every console error and failed request listed. Read only.
//   node journeys/live-demo-screens.mjs --shots <dir> --out <file.json> [--only map,phones] [--settle 3]
import { mkdirSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const shots = arg("shots")
const out = arg("out")
if (!shots || !out) {
  console.error("usage: --shots <dir> --out <file.json>")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const only = arg("only") ? new Set(arg("only").split(",")) : null
const settle = Number(arg("settle", "3")) * 1000
const C = CASES.demo
const screens = [
  ["workspace", "workspace"], ["evidence", "evidence"], ["financial", "financial"],
  ["financial-transactions", "financial?view=transactions"], ["phones", "phones"], ["map", "map"],
  ["timeline", "timeline"], ["graph", "graph"], ["dossiers", "dossiers"], ["search", "search?q=TVN20-118207"],
  ["tasks", "tasks"], ["phone-analyses", "phone-analyses"], ["agent", "agent"], ["reports", "reports"],
]
const login = readLogin()
const browser = await chromium.launch()
const result = { caseId: C, screens: [] }
try {
  const { context } = await signIn(browser, login)
  for (const [name, path] of screens) {
    if (only && !only.has(name)) continue
    const page = await context.newPage()
    await page.setViewportSize({ width: 1440, height: 900 })
    const errors = []
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 240)) })
    page.on("pageerror", (e) => errors.push(`pageerror: ${String(e.message).slice(0, 240)}`))
    page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${new URL(r.url()).pathname}`) })
    const started = Date.now()
    let failed = null
    try {
      await page.goto(`${login.url}/cases/${C}/${path}`, { waitUntil: "domcontentloaded", timeout: 120_000 })
      if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
      await page.waitForLoadState("networkidle", { timeout: 60_000 }).catch(() => {})
      await page.waitForTimeout(settle)
      if (/\/login/.test(page.url())) throw new Error("landed on the sign-in page")
    } catch (e) {
      failed = String(e?.message ?? e).split("\n")[0].slice(0, 240)
    }
    const file = `${shots}/${name}.png`
    await page.screenshot({ path: file }).catch(() => {})
    const heading = await page.locator("h1,h2").first().textContent({ timeout: 1000 }).catch(() => "")
    result.screens.push({ name, path, ms: Date.now() - started, heading: (heading || "").trim().slice(0, 80), failed, errors, file })
    console.log(`${name.padEnd(24)} ${failed ? `FAILED ${failed}` : "ok"}  ${errors.length} console/request errors  ${Math.round((Date.now() - started) / 1000)} s`)
    await page.close()
  }
} finally {
  await browser.close()
}
writeFileSync(out, JSON.stringify(result, null, 1))
