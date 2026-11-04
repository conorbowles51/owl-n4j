#!/usr/bin/env node
// Upload speed of a folder through the live Evidence page (lx-uploadspeed A, D, E, F): signed in once with the jobs
// login over plain http, into the verification case only. Picks the folder with Upload > Folder and records every
// upload request the page makes (method, route, start, end, request bytes, status) from inside the page, so the time
// per stage (hashing, selection create, chunk send, file finish, batch send, registration) comes from the browser's
// own clock. Writes the records to --out as JSON; prints counts and stage times only.
//   node journeys/live-upload-speed.mjs --path <folder> --out <file.json>
//     [--discard]          stop before registration (the finish request is refused in the browser) and discard the
//                          upload with the page's own Discard upload button, so nothing is added to Evidence
//     [--pause-at <n>]     when <n> files are saved, press Pause upload, wait 20 s, press Resume upload
//     [--beside <n>]       open the case's Evidence page in a second tab <n> times during sending, and <n> times before
//                          the pick, timing each until its file list shows
//     [--minutes 120]
import { writeFileSync } from "node:fs"
import { basename } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const flag = (name) => process.argv.includes(`--${name}`)
const path = arg("path")
const out = arg("out")
if (!path || !out) {
  console.error("usage: --path <folder> --out <file.json> [--discard] [--pause-at n] [--beside n]")
  process.exit(2)
}
const discard = flag("discard")
const pauseAt = Number(arg("pause-at", "0"))
const beside = Number(arg("beside", "0"))
const minutes = Number(arg("minutes", "120"))
const caseId = CASES.verification
const name = basename(path)
const login = readLogin()
const browser = await chromium.launch()
let t0 = Date.now()
const secs = () => ((Date.now() - t0) / 1000).toFixed(1)
const result = { name, caseId, discard, pauseAt, events: [], beside: { before: [], during: [] } }
let failed = null

// Inside the page: every upload request, timed with the page's own clock.
const recorder = () => {
  window.__uploadLog = []
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url
    if (!/\/api\/evidence-upload-(sessions|groups)/.test(url)) return original(input, init)
    const body = init?.body
    const entry = {
      m: (init?.method || "GET").toUpperCase(),
      u: url.replace(/^https?:\/\/[^/]+/, ""),
      s: Date.now(),
      b: body instanceof Blob ? body.size : typeof body === "string" ? body.length : 0,
    }
    window.__uploadLog.push(entry)
    try {
      const response = await original(input, init)
      entry.e = Date.now()
      entry.st = response.status
      if (entry.m === "POST" && /\/api\/evidence-upload-groups$/.test(entry.u.split("?")[0]) && response.ok)
        response.clone().json().then((g) => (entry.group = g.id)).catch(() => {})
      return response
    } catch (error) {
      entry.e = Date.now()
      entry.st = 0
      throw error
    }
  }
}

async function timeEvidencePage(context) {
  const page = await context.newPage()
  const s = Date.now()
  try {
    await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
    await page.getByRole("button", { name: /^Upload/ }).first().waitFor({ timeout: 60000 })
    await page.getByRole("row").nth(1).waitFor({ timeout: 60000 }).catch(() => {})
    return Date.now() - s
  } catch {
    return -1
  } finally {
    await page.close()
  }
}

try {
  const { context } = await signIn(browser, login)
  for (let i = 0; i < beside; i++) result.beside.before.push(await timeEvidencePage(context))
  if (beside) console.log(`evidence page before upload (ms): ${result.beside.before.join(", ")}`)
  const page = await context.newPage()
  await page.addInitScript(recorder)
  if (discard)
    await page.route(/\/api\/evidence-upload-groups\/[^/]+\/complete$/, (route) =>
      route.request().method() === "POST" ? route.abort("failed") : route.continue())
  await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  await page.getByRole("button", { name: /^Upload/ }).first().click()
  const chooser = page.waitForEvent("filechooser")
  await page.getByRole("menuitem", { name: "Folder", exact: true }).click()
  const handed = Date.now()
  await (await chooser).setFiles(path, { timeout: 60 * 60_000 })
  if (await page.getByRole("menu").count()) await page.keyboard.press("Escape")
  t0 = Date.now()
  result.pickedAt = t0
  result.handMs = t0 - handed
  console.log(`folder handed to the page in ${(result.handMs / 1000).toFixed(1)} s`)
  const row = page.locator("div.rounded-lg").filter({ has: page.getByText(name, { exact: true }) }).last()
  const deadline = Date.now() + minutes * 60_000
  let paused = false
  let besideDone = 0
  let lastLine = ""
  while (Date.now() < deadline) {
    const log = await page.evaluate(() => window.__uploadLog.map((e) => ({ m: e.m, u: e.u, st: e.st })))
    const groupComplete = log.find((e) => e.m === "POST" && /\/api\/evidence-upload-groups\/[^/]+\/complete$/.test(e.u))
    if (groupComplete && groupComplete.st === 200) {
      result.events.push({ at: Date.now(), what: "registered" })
      console.log(`${secs()} s registered`)
      break
    }
    if (discard && groupComplete && groupComplete.st === 0) {
      result.events.push({ at: Date.now(), what: "sent; registration refused in the browser" })
      console.log(`${secs()} s every file sent; discarding`)
      await page.reload({ waitUntil: "domcontentloaded" })
      const target = page.locator("div.rounded-lg").filter({ has: page.getByText(name, { exact: true }) }).last()
      await target.getByRole("button", { name: "Discard upload" }).click({ timeout: 60000 })
      await target.getByRole("alertdialog", { name: "Discard this upload" }).getByRole("button", { name: "Discard upload" }).click()
      const toast = await page.getByText(/Upload discarded\. [\d,]+ saved files? (was|were) removed/).first()
        .textContent({ timeout: 120000 })
      result.events.push({ at: Date.now(), what: toast })
      console.log(`${secs()} s ${toast}`)
      break
    }
    const sending = log.some((e) => /\/chunks\/|\/batch$/.test(e.u))
    if (sending && besideDone < beside) {
      result.beside.during.push(await timeEvidencePage(context))
      besideDone++
      if (besideDone === beside) console.log(`evidence page during upload (ms): ${result.beside.during.join(", ")}`)
    }
    const line = await row.getByText(/[\d,]+ of [\d,]+ files verified/).first().textContent({ timeout: 1000 }).catch(() => "")
    const saved = Number((line.match(/^([\d,]+) of/)?.[1] || "0").replaceAll(",", ""))
    if (line && line !== lastLine) {
      lastLine = line
      console.log(`${secs()} s   ${line}`)
    }
    if (pauseAt && !paused && saved >= pauseAt) {
      paused = true
      await row.getByRole("button", { name: "Pause upload" }).click()
      result.events.push({ at: Date.now(), what: `paused at ${saved}` })
      console.log(`${secs()} s paused at ${saved} saved`)
      await page.waitForTimeout(20000)
      await row.getByRole("button", { name: "Resume upload" }).click()
      result.events.push({ at: Date.now(), what: "resumed" })
      console.log(`${secs()} s resumed`)
    }
    const alert = await page.getByRole("alert").first().textContent({ timeout: 300 }).catch(() => "")
    if (alert && /could not|failed|changed|missing|refused|Reselect/i.test(alert) && !discard) {
      failed = `page error: ${alert.slice(0, 300)}`
      break
    }
    await page.waitForTimeout(5000)
  }
  if (!failed && !result.events.length) failed = `not finished within ${minutes} min`
  result.log = await page.evaluate(() => window.__uploadLog)
} catch (e) {
  failed = String(e?.message ?? e).split("\n")[0].slice(0, 300)
} finally {
  await browser.close()
}
result.failed = failed
writeFileSync(out, JSON.stringify(result))
console.log(`SUMMARY ${failed ? `FAILED ${failed}` : "finished"} requests=${result.log?.length ?? 0}`)
process.exit(failed ? 1 : 0)
