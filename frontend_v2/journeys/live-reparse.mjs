#!/usr/bin/env node
// Live check of the independent re-parse (05 17.3, stage J item E): signed in once with the jobs login over plain
// http, in the restricted phone reference cases only (CB-INDEX P3). Opens "Read again by an independent tool", presses
// "Read again with ALEAPP/iLEAPP" for one phone (picked by extraction id: the list is in the API's order) and watches
// the phone's line until the run finishes or fails. Prints the run's status words and numbers only; the phone's name
// is masked in the screenshots.
//   node journeys/live-reparse.mjs --case phoneRef1|phoneRef2|phoneRef3 --extraction <id> --shots <dir> --label P12
//     [--minutes 240]
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { PHONE_REFERENCE_CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const caseId = PHONE_REFERENCE_CASES[arg("case")]
const extraction = arg("extraction")
const shots = arg("shots")
const label = arg("label", "phone")
const minutes = Number(arg("minutes", "240"))
if (!caseId || !extraction || !shots) {
  console.error("usage: --case phoneRef1|phoneRef2|phoneRef3 --extraction <id> --shots <dir> --label <short>")
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
  const section = page.getByRole("region", { name: "Re-parse runs" })
  await section.waitFor({ timeout: 60000 })
  const order = await page.evaluate(async (c) => {
    const r = await fetch(`/api/phones/reparse/runs?case_id=${c}`, { headers: { Authorization: `Bearer ${localStorage.getItem("authToken")}` } })
    return (await r.json()).phones.map((p) => p.extraction_id)
  }, caseId)
  const k = order.indexOf(extraction)
  if (k < 0) throw new Error("this extraction is not in the case's phone list")
  const item = section.getByTestId("reparse-phone").nth(k)
  const shoot = async (what) => {
    const file = `${shots}/${label}-reparse-${what}.png`
    const ok = await item.screenshot({ path: file, mask: [item.locator("p.font-medium")], maskColor: "#888", timeout: 30000 })
      .then(() => true).catch(() => false)
    return ok ? file.split("/").pop() : "not taken"
  }
  const button = item.getByRole("button", { name: /^Read again with (ALEAPP|iLEAPP)$/ })
  if (await button.isEnabled()) {
    console.log(`${secs()} s pressed "${(await button.textContent()).trim()}"`)
    await button.click()
  } else {
    console.log(`${secs()} s a run is already open for this phone; watching it`)
  }
  const line = item.locator("p").nth(1)
  const deadline = Date.now() + minutes * 60_000
  let last = ""
  while (Date.now() < deadline) {
    const text = ((await line.textContent({ timeout: 5000 }).catch(() => "")) ?? "").trim()
    if (text && text !== last) {
      last = text
      console.log(`${secs()} s ${text.slice(0, 300)}`)
    }
    if (/finished in|failed:/.test(text)) break
    await page.waitForTimeout(30000)
    await page.reload({ waitUntil: "domcontentloaded" })
    await section.waitFor({ timeout: 60000 }).catch(() => null)
  }
  if (!/finished in/.test(last)) failed = /failed:/.test(last) ? "the run failed" : `not finished within ${minutes} min`
  console.log(`screenshot ${await shoot("end")}`)
} catch (e) {
  failed = String(e.message || e).slice(0, 200)
} finally {
  await browser.close()
}
console.log(`SUMMARY ${label} ${failed ? `FAILED ${failed}` : "finished"}`)
process.exit(failed ? 1 : 0)
