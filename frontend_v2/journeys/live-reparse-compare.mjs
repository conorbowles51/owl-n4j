#!/usr/bin/env node
// Live check of the re-parse comparison (05 17.3, stage J item F): signed in once with the jobs login over plain
// http, in a restricted phone reference case only (CB-INDEX P3). Opens "Read again by an independent tool", presses
// Run, waits until the run completes or stops, then prints each tab's label with its count. Prints counts and status
// words only; the result list is masked in the screenshot.
//   node journeys/live-reparse-compare.mjs --case phoneRef1|phoneRef2|phoneRef3 --shots <dir> --label P12 [--minutes 60]
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { PHONE_REFERENCE_CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const caseId = PHONE_REFERENCE_CASES[arg("case")]
const shots = arg("shots")
const label = arg("label", "phone")
const minutes = Number(arg("minutes", "60"))
if (!caseId || !shots) {
  console.error("usage: --case phoneRef1|phoneRef2|phoneRef3 --shots <dir> --label <short>")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const login = readLogin()
const browser = await chromium.launch()
let failed = null
const t0 = Date.now()
const secs = () => ((Date.now() - t0) / 1000).toFixed(0)
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  await page.goto(`${login.url}/cases/${caseId}/phone-analyses/read-again`, { waitUntil: "domcontentloaded" })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  const root = page.getByTestId("reparse-result-page")
  await root.waitFor({ timeout: 60000 })
  const control = root.locator('[data-part="run"]')
  const before = ((await control.textContent()) ?? "").trim()
  const run = control.getByRole("button", { name: "Run", exact: true })
  await run.waitFor({ timeout: 30000 })
  if (!(await run.isEnabled())) throw new Error("Run is not enabled (a run is open)")
  await run.click()
  console.log(`${secs()} s pressed Run`)
  // wait until the control leaves its earlier words and shows a finished or stopped run
  const deadline = Date.now() + minutes * 60_000
  let last = ""
  while (Date.now() < deadline) {
    const text = ((await control.textContent()) ?? "").trim()
    if (text !== last) {
      last = text
      console.log(`${secs()} s ${text.replace(/RunCancel|Run/g, "").slice(0, 200)}`)
    }
    if (text !== before && /Last run|The last run stopped/.test(text) && !/Cancel/.test(text)) break
    await page.waitForTimeout(5000)
  }
  if (!/Last run/.test(last) || last === before) failed = /stopped/.test(last) ? "the run stopped" : `not finished within ${minutes} min`
  const tabs = root.getByRole("tab")
  const n = await tabs.count()
  const words = []
  for (let k = 0; k < n; k++) words.push(((await tabs.nth(k).textContent()) ?? "").trim())
  console.log(`tabs: ${words.join("; ")}`)
  const file = `${shots}/${label}-compare-end.png`
  const ok = await root.screenshot({ path: file, fullPage: false, mask: [root.locator("ul")], maskColor: "#888", timeout: 30000 })
    .then(() => true).catch(() => false)
  console.log(`screenshot ${ok ? file.split("/").pop() : "not taken"}`)
} catch (e) {
  failed = String(e.message || e).slice(0, 200)
} finally {
  await browser.close()
}
console.log(`SUMMARY ${label} ${failed ? `FAILED ${failed}` : "finished"}`)
process.exit(failed ? 1 : 0)
