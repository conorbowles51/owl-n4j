#!/usr/bin/env node
// Phones together on the live site (lx-phonetogether E): Map, Timeline and Conversations with the overlays on, read only.
//   node journeys/live-phonetogether.mjs --case demo|ref1 --shots <dir> --out <file.json> [--width 1500]
import { mkdirSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, PHONE_REFERENCE_CASES, readLogin, signIn } from "./lib.mjs"

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d }
const which = arg("case", "demo")
const shots = arg("shots"); const out = arg("out"); const width = Number(arg("width", "1500"))
mkdirSync(shots, { recursive: true })
const login = readLogin()
const C = which === "demo" ? CASES.demo : Object.values(PHONE_REFERENCE_CASES)[0]
const res = { case: which, caseId: C, width, steps: [] }
const step = (name, data) => { res.steps.push({ name, ...data }); console.log(name, JSON.stringify(data).slice(0, 400)) }
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  await page.setViewportSize({ width, height: width > 800 ? 900 : 844 })
  const errors = []
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)) })
  page.on("pageerror", (e) => errors.push(`pageerror ${String(e.message).slice(0, 200)}`))
  const base = login.url
  const q = "phone_layers=on&phone_together=on"
  const shot = (n) => page.screenshot({ path: `${shots}/${which}-${width}-${n}.png`, timeout: 120000 }).catch((e) => console.log("shot failed", n, String(e).slice(0, 80)))
  const panelText = async () => (await page.getByTestId("together-panel").first().innerText({ timeout: 90000 }).catch(() => "")).replace(/\n/g, " | ")
  const waitDone = () => page.waitForFunction(() => { const t = document.querySelector("[data-testid=together-panel]"); return t && !/^Reading where/.test(t.textContent || "") }, null, { timeout: 120000 }).catch(() => {})
  // Map
  await page.goto(`${base}/cases/${C}/map?${q}`, { waitUntil: "domcontentloaded" })
  await page.waitForSelector("[data-testid=together-bar]", { timeout: 90000 }).catch(() => {})
  await waitDone(); await page.waitForTimeout(3000)
  const t = await panelText()
  step("map panel", { head: t.slice(0, 260), meetings: (await page.getByTestId("together-meeting").count()), corroborate: await page.getByRole("button", { name: /Corroborate/ }).count() })
  await shot("map")
  // Timeline
  if (which === "demo") {
    for (const [name, path] of [["timeline", "timeline"], ["conversations", "conversations"]]) {
      await page.goto(`${base}/cases/${C}/${path}?${q}`, { waitUntil: "domcontentloaded" })
      if (name === "timeline") await page.getByRole("button", { name: /^Phones \(/ }).click({ timeout: 30000 }).catch(() => {})
      await page.waitForSelector("[data-testid=together-panel]", { timeout: 90000 }).catch(() => {})
      await waitDone(); await page.waitForTimeout(3000)
      step(name, { band: (await page.getByTestId("together-band").innerText().catch(() => "")).replace(/\n/g, " | ").slice(0, 200), panel: (await panelText()).slice(0, 300),
        meetings: await page.getByTestId("together-meeting").count(), contacts: await page.getByTestId("together-contact").count(), relays: await page.getByTestId("together-relay").count() })
      await shot(name)
    }
  }
  // the read, timed on the real path (ref1: the two phones with most positions)
  const sum = await page.evaluate(async ([c]) => (await fetch("/api/phones/map/summary", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ case_id: c, filter: {} }) })).json(), [C])
  const top = (sum.by_phone ?? []).sort((a, b) => b.positioned - a.positioned).slice(0, 2).map((b) => b.extraction_id)
  const times = await page.evaluate(async ([c, ph]) => { const o = []; let body = null; for (let i = 0; i < 20; i++) { const t0 = performance.now(); const r = await fetch(`/api/cases/${c}/relation-overlaps?phones=${ph.join(",")}`); body = await r.json(); o.push(Math.round(performance.now() - t0)) } return { o, message: body.message, meetings: body.together?.length, contacts: body.shared_contacts?.length, relays: body.relay_chains?.length } }, [C, top])
  const s = [...times.o].sort((a, b) => a - b)
  step("read timing, two phones with most positions", { n: s.length, p50: s[10], p95: s[18], max: s[19], message: times.message, meetings: times.meetings, contacts: times.contacts, relays: times.relays })
  step("console errors", { count: errors.length, errors })
} finally {
  writeFileSync(out, JSON.stringify(res, null, 1))
  await browser.close()
}
