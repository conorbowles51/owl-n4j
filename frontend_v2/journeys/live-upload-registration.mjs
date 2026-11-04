#!/usr/bin/env node
// Folder registration and Delete Folder through the live Evidence page (lx-uploadfollow G): signed in once with the
// jobs login over plain http, in the verification case only. Picks the folder with Upload > Folder, records every
// upload request with the page's own clock, and every distinct upload progress line the page shows (so the
// "Registering n of N files" text is captured as the user sees it). Then opens Delete Folder on the uploaded folder
// (its files sit only in subfolders), records the count the dialog states and screenshots it, and presses Delete
// Folder: the jobs login has no evidence delete, so the refusal the page shows is recorded too.
//   node journeys/live-upload-registration.mjs --path <folder> --out <file.json> [--minutes 90] [--dialog-only]
import { writeFileSync } from "node:fs"
import { basename } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const path = arg("path")
const out = arg("out")
if (!path || !out) {
  console.error("usage: --path <folder> --out <file.json> [--minutes 90] [--dialog-only]")
  process.exit(2)
}
const minutes = Number(arg("minutes", "90"))
const caseId = CASES.verification
const name = basename(path)
const login = readLogin()
const browser = await chromium.launch()
const result = { name, caseId, lines: [], events: [] }
let failed = null
const stamp = () => new Date().toISOString()

const recorder = () => {
  window.__uploadLog = []
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url
    if (!/\/api\/evidence-(upload-groups|folders)/.test(url)) return original(input, init)
    const entry = { m: (init?.method || "GET").toUpperCase(), u: url.replace(/^https?:\/\/[^/]+/, ""), s: Date.now() }
    window.__uploadLog.push(entry)
    try {
      const response = await original(input, init)
      entry.e = Date.now()
      entry.st = response.status
      return response
    } catch (error) {
      entry.e = Date.now()
      entry.st = 0
      throw error
    }
  }
}

async function deleteDialog(page) {
  await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
  const node = page.getByText(name, { exact: true }).first()
  await node.waitFor({ timeout: 120000 })
  await node.click({ button: "right" })
  await page.getByRole("menuitem", { name: "Delete", exact: true }).click({ timeout: 30000 })
  const dialog = page.getByRole("dialog")
  const count = await dialog.getByText(/will be permanently deleted|There are no files/).textContent({ timeout: 120000 })
  result.dialog = count
  console.log(`${stamp()} delete dialog: ${count}`)
  await page.screenshot({ path: `${out}.dialog.png` })
  await dialog.getByRole("button", { name: "Delete Folder" }).click({ timeout: 60000 })
  const refusal = await dialog.getByRole("alert").textContent({ timeout: 120000 }).catch(() => "")
  result.refusal = refusal
  console.log(`${stamp()} after Delete Folder: ${refusal || "(no refusal shown)"}`)
  await page.screenshot({ path: `${out}.refused.png` })
  result.folderStillListed = (await page.getByText(name, { exact: true }).count()) > 0
}

try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  await page.addInitScript(recorder)
  if (!process.argv.includes("--dialog-only")) {
    await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
    if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
    await page.getByRole("button", { name: /^Upload/ }).first().click()
    const chooser = page.waitForEvent("filechooser")
    await page.getByRole("menuitem", { name: "Folder", exact: true }).click()
    await (await chooser).setFiles(path, { timeout: 60 * 60_000 })
    if (await page.getByRole("menu").count()) await page.keyboard.press("Escape")
    result.pickedAt = Date.now()
    console.log(`${stamp()} folder handed to the page`)
    const deadline = Date.now() + minutes * 60_000
    let shot = false
    while (Date.now() < deadline) {
      const texts = await page.getByText(/^(Checking files before upload|Sending |All [\d,]+ files arrived|Registering )/)
        .allTextContents().catch(() => [])
      for (const text of texts)
        if (!result.lines.length || result.lines.at(-1).text !== text) {
          result.lines.push({ at: Date.now(), text })
          if (/^Registering|^All/.test(text)) console.log(`${stamp()} ${text}`)
          if (/^Registering [\d,]+ of/.test(text) && !shot) {
            shot = true
            await page.screenshot({ path: `${out}.registering.png` })
          }
        }
      const receipt = await page.getByText(/Uploaded [\d,]+ files\./).first().textContent({ timeout: 300 }).catch(() => "")
      if (receipt) {
        result.receipt = receipt
        result.events.push({ at: Date.now(), what: "registered" })
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
    if (!failed && !result.events.length) failed = `not finished within ${minutes} min`
    result.log = await page.evaluate(() => window.__uploadLog)
  }
  if (!failed) await deleteDialog(page)
} catch (e) {
  failed = String(e?.message ?? e).split("\n")[0].slice(0, 300)
} finally {
  await browser.close()
}
result.failed = failed
writeFileSync(out, JSON.stringify(result))
console.log(`SUMMARY ${failed ? `FAILED ${failed}` : "finished"}`)
process.exit(failed ? 1 : 0)
