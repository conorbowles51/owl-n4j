#!/usr/bin/env node
// Upload a folder of the demo case's documents or statements through the live Evidence page (lx-demo D), as a person
// does it: signed in once with the jobs login over plain http, Upload > Folder, into the demo case only. Waits for the
// page's receipt ("Uploaded n files.") and prints each distinct progress line. Prints counts and page lines only.
//   node journeys/live-demo-upload.mjs --path <folder> --out <file.json> [--minutes 60]
// The folder must come from `fixture_builder.py demo` (its PDFs carry the SYNTHETIC banner), or nothing is uploaded.
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const path = arg("path")
const out = arg("out")
if (!path || !out) {
  console.error("usage: --path <folder> --out <file.json> [--minutes 60]")
  process.exit(2)
}
const minutes = Number(arg("minutes", "60"))
const caseId = CASES.demo
const files = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : [join(dir, n)]))
const pdfs = files(path).filter((f) => f.endsWith(".pdf"))
if (!pdfs.length || !pdfs.every((f) => readFileSync(f).includes("SYNTHETIC"))) {
  console.error("refused: every PDF in the folder must carry the demo's SYNTHETIC banner")
  process.exit(2)
}
const login = readLogin()
const browser = await chromium.launch()
const result = { path, caseId, lines: [] }
let failed = null
const stamp = () => new Date().toISOString()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  await page.getByRole("button", { name: /^Upload/ }).first().click()
  const chooser = page.waitForEvent("filechooser")
  await page.getByRole("menuitem", { name: "Folder", exact: true }).click()
  await (await chooser).setFiles(path, { timeout: 10 * 60_000 })
  if (await page.getByRole("menu").count()) await page.keyboard.press("Escape")
  console.log(`${stamp()} folder handed to the page`)
  const deadline = Date.now() + minutes * 60_000
  while (Date.now() < deadline) {
    const texts = await page.getByText(/^(Checking files before upload|Sending |All [\d,]+ files arrived|Registering )/)
      .allTextContents().catch(() => [])
    for (const text of texts)
      if (!result.lines.length || result.lines.at(-1).text !== text) {
        result.lines.push({ at: Date.now(), text })
        console.log(`${stamp()} ${text}`)
      }
    const receipt = await page.getByText(/Uploaded [\d,]+ files?\./).first().textContent({ timeout: 300 }).catch(() => "")
    if (receipt) {
      result.receipt = receipt
      console.log(`${stamp()} receipt: ${receipt}`)
      break
    }
    const alert = await page.getByRole("alert").first().textContent({ timeout: 300 }).catch(() => "")
    if (alert && /could not|failed|changed|missing|refused|Reselect|stopped/i.test(alert)) {
      failed = `page error: ${alert.slice(0, 300)}`
      break
    }
    await page.waitForTimeout(1000)
  }
  if (!failed && !result.receipt) failed = `not finished within ${minutes} min`
  await page.screenshot({ path: `${out}.png` })
} catch (e) {
  failed = String(e?.message ?? e).split("\n")[0].slice(0, 300)
} finally {
  await browser.close()
}
result.failed = failed
writeFileSync(out, JSON.stringify(result))
console.log(`SUMMARY ${failed ? `FAILED ${failed}` : "finished"}`)
process.exit(failed ? 1 : 0)
