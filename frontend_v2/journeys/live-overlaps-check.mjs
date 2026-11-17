#!/usr/bin/env node
// lx-overlaps I: in the demo case, as a person does over plain http, signed in: mark a payment on the ledger with
// "Look into how these relate", see the result page, find the tray on another screen, export the report.
//   node journeys/live-overlaps-check.mjs --shots <dir> [--width 1500]
import { mkdirSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (n, f) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : f }
const shots = arg("shots"); const width = Number(arg("width", "1500")); const height = width < 600 ? 800 : 900
mkdirSync(shots, { recursive: true })
const C = CASES.demo; const base = readLogin().url
const log = []; const note = (s) => { log.push(s); console.log(s) }
let lastPage = null
const context_page_shot = async () => { try { await lastPage?.screenshot({ path: `${shots}/${width}-failed.png` }) } catch { /* none */ } }
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, readLogin())
  const page = await context.newPage()
  lastPage = page
  await page.setViewportSize({ width, height })
  const errors = []
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)) })
  page.on("pageerror", (e) => errors.push(`pageerror: ${String(e.message).slice(0, 200)}`))
  await page.goto(`${base}/cases/${C}/financial?view=transactions`, { waitUntil: "domcontentloaded" })
  await page.locator('input[type="checkbox"]').first().waitFor({ state: "attached", timeout: 90000 })
  await page.waitForTimeout(8000)
  await page.locator('input[type="checkbox"]').first().evaluate((e) => e.click()) // the card's checkbox is drawn over by its label
  const button = page.getByRole("button", { name: /Look into how these relate|Relate…/ }).first()
  await button.waitFor({ state: "visible", timeout: 60000 })
  await page.screenshot({ path: `${shots}/${width}-1-ledger.png` })
  await button.click()
  await page.getByRole("button", { name: "Start a new look" }).click()
  const t0 = Date.now()
  await page.getByRole("heading", { name: "How these items could be linked" }).waitFor({ timeout: 30000 })
  note(`result page open ${Date.now() - t0} ms after Start`)
  await page.getByTestId("relation-summary").waitFor({ timeout: 120000 })
  note(`analysis done ${Date.now() - t0} ms after Start: ${(await page.getByTestId("relation-summary").innerText()).slice(0, 220)}`)
  await page.screenshot({ path: `${shots}/${width}-2-result.png`, fullPage: true })
  const download = page.waitForEvent("download", { timeout: 60000 })
  await page.getByRole("button", { name: /Export report/ }).click()
  const d = await download
  await d.saveAs(`${shots}/${width}-link-analysis.pdf`)
  note(`report downloaded: ${d.suggestedFilename()}`)
  // a second screen: the Timeline's own button adds its range to the look in progress, so the group grows
  await page.goto(`${base}/cases/${C}/timeline`, { waitUntil: "domcontentloaded" })
  await page.getByText(/Looking into how 1 items relate/).waitFor({ timeout: 60000 })
  await page.screenshot({ path: `${shots}/${width}-3-tray-on-timeline.png` })
  const look = page.getByRole("button", { name: /Look into how these relate|Relate…/ }).first()
  await look.waitFor({ state: "visible", timeout: 90000 })
  await look.click()
  await page.getByRole("button", { name: /Add to the look in progress \(1 items\)/ }).click()
  await page.getByTestId("relation-summary").waitFor({ timeout: 180000 })
  note(`after adding from the timeline: ${(await page.getByTestId("relation-summary").innerText()).slice(0, 200)}`)
  await page.screenshot({ path: `${shots}/${width}-4-grown-result.png`, fullPage: true })
  await page.goto(`${base}/cases/${C}/graph`, { waitUntil: "domcontentloaded" })
  await page.getByText(/Looking into how \d+ items relate/).waitFor({ timeout: 60000 })
  note("tray shown on the graph screen")
  await page.screenshot({ path: `${shots}/${width}-5-tray-on-graph.png` })
  note(`console errors: ${errors.length}${errors.length ? " " + JSON.stringify(errors.slice(0, 3)) : ""}`)
} catch (e) {
  note(`FAILED: ${e.message.split("\n")[0]}`)
  await context_page_shot()
  process.exitCode = 1
} finally {
  writeFileSync(`${shots}/${width}-log.txt`, log.join("\n"))
  await browser.close()
}
