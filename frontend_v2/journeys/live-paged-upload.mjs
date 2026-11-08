#!/usr/bin/env node
// Live check of a folder whose file list is larger than one manifest page (01 D41): signed in once with the jobs
// login over plain http, in the verification case only, with an invented folder of tiny files. Watches the hashing
// panel, records every upload-group request the page makes (method, status, member counts, declared total), waits
// for sending to begin (so the paged registration is complete), then discards the selection through the page's own
// Discard so nothing is registered as evidence. Prints one line per stage and writes a JSON result.
//   node journeys/live-paged-upload.mjs --path <folder> --out <file.json> --shots <dir> [--minutes 30]
import { mkdirSync, writeFileSync } from "node:fs"
import { basename } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const path = arg("path")
const out = arg("out")
const shots = arg("shots")
if (!path || !out || !shots) {
  console.error("usage: --path <folder> --out <file.json> --shots <dir> [--minutes 30]")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const minutes = Number(arg("minutes", "30"))
const caseId = CASES.verification
const name = basename(path)
const login = readLogin()
const browser = await chromium.launch()
const result = { name, caseId, lines: [], groupRequests: [] }
let failed = null
const stamp = () => new Date().toISOString()

const recorder = () => {
  window.__groupLog = []
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url
    if (!/\/api\/evidence-upload-groups/.test(url)) return original(input, init)
    const entry = { m: (init?.method || "GET").toUpperCase(), u: url.replace(/^https?:\/\/[^/]+/, "") }
    try {
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : null
      if (body?.members) entry.n = body.members.length
      if (body?.members_total != null) entry.total = body.members_total
    } catch { /* bodies that are not JSON carry no counts */ }
    window.__groupLog.push(entry)
    const response = await original(input, init)
    entry.st = response.status
    return response
  }
}

let page = null
try {
  const { context } = await signIn(browser, login)
  page = await context.newPage()
  await page.addInitScript(recorder)
  await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  await page.getByRole("button", { name: /^Upload/ }).first().click()
  const chooser = page.waitForEvent("filechooser")
  await page.getByRole("menuitem", { name: "Folder", exact: true }).click()
  await (await chooser).setFiles(path, { timeout: 60 * 60_000 })
  if (await page.getByRole("menu").count()) await page.keyboard.press("Escape")
  console.log(`${stamp()} folder handed to the page`)
  const deadline = Date.now() + minutes * 60_000
  let hashingShot = false
  let sending = false
  while (Date.now() < deadline && !sending) {
    const texts = await page
      .getByText(/^(Checking files before upload|Sending )/)
      .allTextContents()
      .catch(() => [])
    for (const text of texts) {
      if (!result.lines.length || result.lines.at(-1).text !== text) result.lines.push({ at: Date.now(), text })
      if (/^Checking files before upload/.test(text) && !hashingShot) {
        hashingShot = true
        console.log(`${stamp()} ${text}`)
        await page.screenshot({ path: `${shots}/paged-01-hashing.png` })
      }
      if (/^Sending /.test(text)) {
        sending = true
        console.log(`${stamp()} ${text}`)
        await page.screenshot({ path: `${shots}/paged-02-sending.png` })
      }
    }
    const alert = await page.getByRole("alert").first().textContent({ timeout: 300 }).catch(() => "")
    if (alert && /could not|failed|changed|missing|refused|Reselect|stopped/i.test(alert)) {
      failed = `page error: ${alert.slice(0, 300)}`
      break
    }
    await page.waitForTimeout(1000)
  }
  if (!sending && !failed) failed = `sending did not begin within ${minutes} min`
  result.groupRequests = await page.evaluate(() => window.__groupLog)
  if (!failed) {
    // the server's view of the selection, through the page's own session
    const listed = await page.evaluate(async (c) => {
      const r = await fetch(`/api/evidence-upload-groups?case_id=${c}`)
      return r.json()
    }, caseId)
    result.group = listed.map((g) => ({ file_count: g.file_count, members_total: g.members_total, status: g.status }))
      .find((g) => g.members_total != null)
    console.log(`${stamp()} listed: ${JSON.stringify(result.group)}`)
    const discard = page.getByRole("button", { name: "Discard upload" }).first()
    await discard.click({ timeout: 60000 })
    await page.getByRole("alertdialog", { name: "Discard this upload" }).getByRole("button", { name: "Discard upload" })
      .click({ timeout: 30000 })
    await page.waitForTimeout(3000)
    const after = await page.evaluate(async (c) => {
      const r = await fetch(`/api/evidence-upload-groups?case_id=${c}`)
      return r.json()
    }, caseId)
    result.discarded = !after.some((g) => g.members_total != null)
    console.log(`${stamp()} discarded: ${result.discarded}`)
    await page.screenshot({ path: `${shots}/paged-03-discarded.png` })
    if (!result.discarded) failed = "the selection was still listed after Discard"
  }
} catch (e) {
  failed = String(e?.message ?? e).split("\n")[0].slice(0, 300)
  if (page) {
    result.failedAt = page.url()
    await page.screenshot({ path: `${shots}/paged-00-failed.png` }).catch(() => {})
  }
} finally {
  await browser.close()
}
result.failed = failed
writeFileSync(out, JSON.stringify(result, null, 1))
console.log(`SUMMARY ${failed ? `FAILED ${failed}` : "finished"}`)
process.exit(failed ? 1 : 0)
