#!/usr/bin/env node
// Live check of a real phone report upload (cb-capture H): signed in once with the jobs login over plain http, into
// one of the restricted phone reference cases only (CB-INDEX P3). Picks a folder or a ZIP, watches the hashing and sending panels and the readiness card
// to the end, and prints one line per stage seen with seconds since the pick. Prints counts and stage words only,
// never the report's name or page text beyond the card's step lines (which hold counts). Screenshots are of the
// evidence page with every element naming the report masked.
//   node journeys/live-phone-upload.mjs --kind folder|zip --path <path> --shots <dir> --label <short>
//     --case phoneRef1|phoneRef2|phoneRef3 [--minutes 90]
// A synthetic report from tests/phone/fixture_builder.py may go into a synthetic case (--case training|phonesOnly):
// the folder's Report.xml must carry the builder's synthetic mark, or nothing is uploaded.
import { existsSync, mkdirSync, readFileSync } from "node:fs"
import { basename, join } from "node:path"
import { chromium } from "playwright"
import { CASES, PHONE_REFERENCE_CASES, readLogin, signIn } from "./lib.mjs"
import { releaseRunning, stalled } from "./upload-stall.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const kind = arg("kind")
const path = arg("path")
const shots = arg("shots")
const label = arg("label", "report")
const minutes = Number(arg("minutes", "90"))
if (!["folder", "zip"].includes(kind) || !path || !shots) {
  console.error("usage: --kind folder|zip --path <path> --shots <dir> --label <short>")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const name = basename(path)
const SYNTHETIC_CASES = { training: CASES.training, phonesOnly: CASES.phonesOnly }
const isSyntheticReport = () => {
  const report = join(path, "Report.xml")
  return kind === "folder" && existsSync(report) && readFileSync(report, "utf8").slice(0, 20000).includes("SYNTHETIC")
}
const caseId = PHONE_REFERENCE_CASES[arg("case")] ?? (SYNTHETIC_CASES[arg("case")] && isSyntheticReport() ? SYNTHETIC_CASES[arg("case")] : undefined)
if (!caseId) {
  console.error("--case must be phoneRef1, phoneRef2 or phoneRef3, or training or phonesOnly for a synthetic report folder")
  process.exit(2)
}
const login = readLogin()
const browser = await chromium.launch()
let t0 = Date.now()
const secs = () => ((Date.now() - t0) / 1000).toFixed(1)
const seen = []
let failed = null
// A browser call with no timeout of its own held try 3 of P07 silent for 7 h 30 min (5 Nov): its log stayed empty and
// the watch loop never ran. Every step below moves `beat`; a run with no beat for this long ends itself, with words.
const quietMinutes = 90
let beat = Date.now()
const step = (words) => {
  beat = Date.now()
  console.log(`step ${new Date().toISOString().slice(11, 19)} ${words}`)
}
setInterval(() => {
  if (Date.now() - beat < quietMinutes * 60_000) return
  console.log(`SUMMARY ${label} FAILED the browser did not answer for ${quietMinutes} min ${JSON.stringify(seen.map(({ stage, at }) => ({ stage, at })))}`)
  process.exit(1)
}, 60_000).unref()
try {
  const { context } = await signIn(browser, login)
  step("signed in")
  const page = await context.newPage()
  await page.goto(`${login.url}/cases/${caseId}/evidence`, { waitUntil: "domcontentloaded" })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  const masks = () => [page.getByText(name, { exact: false }), page.getByText(name.replace(/\.zip$/i, ""), { exact: false })]
  let shot = 0
  // Screenshots are of this report's own elements only (the case may hold other evidence and jobs), with the report's
  // name masked; when the element cannot be found the screenshot is skipped, never widened to the page.
  const snap = async (what, target) => {
    shot += 1
    const file = `${shots}/${label}-${String(shot).padStart(2, "0")}-${what}.png`
    try {
      await target.screenshot({ path: file, mask: masks(), maskColor: "#888", timeout: 5000 })
      console.log(`${secs()} s screenshot ${file.split("/").pop()}`)
    } catch {
      console.log(`${secs()} s screenshot skipped (${what}: element not found)`)
    }
  }
  // the innermost element holding both the text and the upload card's title
  const uploadCard = (re) => page.locator("div").filter({ has: page.getByText(re) }).filter({ hasText: /(upload|ZIP) \(|upload/i }).last()
  step("evidence page open")
  await page.getByRole("button", { name: "Add phone report (folder or ZIP)" }).click()
  const chooser = page.waitForEvent("filechooser")
  await page.getByRole("menuitem", { name: kind === "folder" ? "Phone report folder" : "Phone report ZIP file" }).click()
  // a folder of 200,000 files takes Playwright minutes to hand to the page; the default 30 s stopped P07 and P03
  await (await chooser).setFiles(path, { timeout: 60 * 60_000 })
  step("selection handed to the page")
  // until the menu closes itself on a pick (3765860e), close it so the page is not left hidden
  // count() has no timeout of its own: this line held P07 try 3 for 7 h 30 min, so it gets one and the watch goes on
  const menuOpen = await Promise.race([page.getByRole("menu").count(), new Promise((done) => setTimeout(() => done(0), 60_000))])
  if (menuOpen) await page.keyboard.press("Escape")
  t0 = Date.now() // the clock starts at the pick
  step("watching")
  const watch = [
    ["hashing", /Checking files before upload: [\d,]+ of [\d,]+|Checking the file before upload: [\d.]+ of [\d.]+ [KMG]?B/],
    ["sending", /Sending [\d.]+ (?:[KMG]B )?of [\d.]+ [KMG]B/],
    ["Checking the report", /Checking the report's fingerprints|Finding the report documents|Counting every element/],
    ["Reading records", /records and [\d,]+ files read/],
    ["Checking nothing is missing", /Comparing every element with the report|Checking the files/],
    ["finished", /Every record was read and checked against the report|already in the case|could not|Stopped at/],
  ]
  // stages after sending are read from this report's own card only (other cards may be on the page)
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const card = page.getByRole("group", { name: new RegExp(`^Phone report: ${esc}`) })
  const scope = (stage) => (["hashing", "sending"].includes(stage) ? page : card)
  const deadline = Date.now() + minutes * 60_000
  let last = ""
  // A selection left paused with nobody to resume it shows a frozen line for ever (P07, 4 Nov: 6 h 8 min silent until
  // a scheduled check found it): a stall ends the run, and the next try's fresh page resumes the selection through the
  // app's own path. Time while a release runs does not count: releases one after another froze the line for 3 h 24 min
  // on 5 Nov, the page would have carried on by itself, and a fresh page has to read every file again.
  const stallMinutes = 90
  let moved = { line: "", at: Date.now() }
  while (Date.now() < deadline) {
    beat = Date.now()
    for (const [stage, re] of watch) {
      if (seen.some((s) => s.stage === stage)) continue
      if (await scope(stage).getByText(re).first().isVisible().catch(() => false)) {
        seen.push({ stage, at: Number(secs()) })
        console.log(`${secs()} s ${stage}`)
        const where = ["hashing", "sending"].includes(stage) ? uploadCard(re) : card.first()
        await snap(stage.replace(/\W+/g, "-").toLowerCase(), where)
      }
    }
    if (seen.some((s) => s.stage === "finished")) break
    if (process.env.LIVE_DEBUG) console.log(`${secs()} s debug cards=${await card.count()} groups=${await page.getByRole("group").count()}`)
    // the card's running step line holds counts only; print it when it changes, at most every 30 s
    // before the card exists, the upload panel's own line (hashing or sending counts) is the running line
    const line = (await card.count())
      ? await card.locator('[aria-live="polite"]').first().textContent({ timeout: 1000 }).catch(() => "")
      : await page.getByText(watch[0][1]).or(page.getByText(watch[1][1])).first().textContent({ timeout: 1000 }).catch(() => "")
    if (line && line !== moved.line) moved = { line, at: Date.now() }
    if (seen.at(-1)?.stage && Date.now() - moved.at > stallMinutes * 60_000 && releaseRunning())
      moved.at = Date.now()
    if (stalled(seen.at(-1)?.stage, moved.at, stallMinutes)) {
      const quietAlert = await page.getByRole("alert").first().textContent({ timeout: 500 }).catch(() => "")
      failed = `no change on the page for ${stallMinutes} min during ${seen.at(-1)?.stage}` +
        (quietAlert ? `; the page says: ${quietAlert.replace(name, "[report]").slice(0, 200)}` : "")
      console.log(`${secs()} s ${failed}`)
      break
    }
    // a changed line counts as shown only once printed, so the log never stays on a line the page has left
    if (line && line !== last && /\d/.test(line)) {
      if (!seen.length || Number(secs()) - (seen.at(-1).printed || 0) >= 30) {
        last = line
        console.log(`${secs()} s   ${line.replace(name, "[report]")}`)
        if (seen.length) seen.at(-1).printed = Number(secs())
      }
    }
    // an error on the page ends the watch with its words (the run would otherwise wait out --minutes)
    const alert = (await page.getByRole("alert").first().textContent({ timeout: 500 }).catch(() => "")) ||
      (await page.getByText(/so it was not uploaded|so nothing was uploaded/).first().textContent({ timeout: 500 }).catch(() => ""))
    if (alert && /could not|failed|error|refused|not uploaded|nothing was uploaded|at most|too many|too large/i.test(alert)) {
      failed = `page error: ${alert.replace(name, "[report]").slice(0, 300)}`
      console.log(`${secs()} s ${failed}`)
      await snap("page-error", page.getByRole("alert").first())
      break
    }
    await page.waitForTimeout(3000)
  }
  if (!failed && !seen.some((s) => s.stage === "finished")) failed = `not finished within ${minutes} min`
  // the end state: the card, the outcome lines and the attention feed
  await page.waitForTimeout(2000)
  await snap("end-card", card.first())
  const outcomes = await card.getByText(/^[\d,]+ files? (match|are|do not|have)/).allTextContents()
  for (const o of outcomes) console.log(`outcome: ${o}`)
  const message = await card.getByText(/Every record was read and checked against the report[^.]*\./).first().textContent().catch(() => "")
  if (message) console.log(`message: ${message.replace(name, "[report]")}`)
  await page.goto(`${login.url}/cases/${caseId}`, { waitUntil: "domcontentloaded" })
  // the feed loads after the page; a fixed wait missed it on a busy server
  await page.getByText(/^Phone report (ready|being read)$/).first().waitFor({ timeout: 30000 }).catch(() => {})
  const feedItem = page.locator("div, li, article").filter({ has: page.getByText(/^Phone report (ready|being read)$/) })
    .filter({ has: page.getByText(name.replace(/\.zip$/i, ""), { exact: false }) }).last()
  await snap("attention-feed-item", feedItem)
} catch (e) {
  failed = String(e?.message ?? e).split("\n")[0].slice(0, 200)
} finally {
  await browser.close()
}
console.log(`SUMMARY ${label} ${failed ? `FAILED ${failed}` : "finished"} ${JSON.stringify(seen.map(({ stage, at }) => ({ stage, at })))}`)
process.exit(failed ? 1 : 0)
