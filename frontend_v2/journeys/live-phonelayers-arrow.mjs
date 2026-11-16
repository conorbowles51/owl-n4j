#!/usr/bin/env node
// Arrow direction on a known route: one phone, its first move under 2 hours and about 1 km, zoomed in (lx-phonelayers G).
import { mkdirSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"
const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d }
const shots = arg("shots"); mkdirSync(shots, { recursive: true })
const login = readLogin(); const C = CASES.demo
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage(); await page.setViewportSize({ width: 1500, height: 900 })
  await page.goto(`${login.url}/cases/${C}/map?phone_layers=on`, { waitUntil: "domcontentloaded" })
  const post = (p, b) => page.evaluate(async ([p, b]) => (await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json(), [p, b])
  const sum = await post("/api/phones/map/summary", { case_id: C, filter: {} })
  const ph = sum.by_phone.find((b) => b.label === "Phone 1")
  const t = await post("/api/phones/map/trajectory", { case_id: C, filter: { phones: [ph.extraction_id] } })
  const km = (a, b) => Math.hypot((a.lat - b.lat) * 111, (a.lon - b.lon) * 85)
  let leg = null
  for (let i = 1; i < t.items.length; i++) {
    const a = t.items[i - 1], b = t.items[i]
    const gap = Date.parse(b.instant) - Date.parse(a.instant)
    if (gap > 0 && gap < 7200_000 && km(a, b) > 0.6 && km(a, b) < 2) { leg = { a, b }; break }
  }
  console.log("leg", JSON.stringify(leg))
  const mid = [(leg.a.lon + leg.b.lon) / 2, (leg.a.lat + leg.b.lat) / 2]
  await page.goto(`${login.url}/cases/${C}/map?phone_layers=on&phones=${ph.extraction_id}&phone_point=${mid[0]},${mid[1]}`, { waitUntil: "domcontentloaded" })
  await page.getByLabel("Show routes").waitFor({ timeout: 90000 })
  await page.getByLabel("Show routes").click()
  await page.getByText(/moves? drawn/).waitFor({ timeout: 90000 })
  await page.waitForTimeout(4000)
  await page.screenshot({ path: `${shots}/demo-1500-arrow-direction.png` })
  writeFileSync(`${shots}/demo-1500-arrow-leg.json`, JSON.stringify({ ...leg, bearing: "from a to b", dlon: leg.b.lon - leg.a.lon, dlat: leg.b.lat - leg.a.lat }, null, 2))
} finally { await browser.close() }
