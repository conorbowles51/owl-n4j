#!/usr/bin/env node
// No loss (lx-phonelayers G): for 3 phones of the demo case, the count each shows alone through the old per-phone screens
// against the count the layer control states for that phone (Map positions, Conversations messages and calls).
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"
const login = readLogin(); const C = CASES.demo
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage(); await page.setViewportSize({ width: 1500, height: 900 })
  await page.goto(`${login.url}/cases/${C}/map?phone_layers=on`, { waitUntil: "domcontentloaded" })
  const post = (p, b) => page.evaluate(async ([p, b]) => (await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json(), [p, b])
  const sum = await post("/api/phones/map/summary", { case_id: C, filter: {} })
  const rows = []
  for (const b of sum.by_phone.slice(0, 3)) {
    const alone = await post("/api/phones/map/summary", { case_id: C, filter: { phones: [b.extraction_id] } })
    // the old per-phone Conversations route: its own count text
    await page.goto(`${login.url}/cases/${C}/phones/${b.extraction_id}/records/conversations`, { waitUntil: "domcontentloaded" })
    await page.waitForSelector("[data-testid=scope-bar]", { timeout: 90000 })
    await page.waitForFunction(() => !/Counting/.test(document.querySelector("[data-testid=scope-bar]")?.innerText ?? "Counting"), null, { timeout: 90000 })
    const old = (await page.getByTestId("scope-bar").innerText()).replace(/\n/g, " ")
    // the new case-level view with this phone alone on
    await page.goto(`${login.url}/cases/${C}/conversations?phone_layers=on&phones=${b.extraction_id}`, { waitUntil: "domcontentloaded" })
    await page.waitForSelector("[data-testid=phone-layers]", { timeout: 90000 })
    await page.waitForFunction(() => !/Counting/.test(document.querySelector("[data-testid=scope-bar]")?.innerText ?? "Counting"), null, { timeout: 90000 })
    await page.waitForTimeout(3000)
    const nw = (await page.getByTestId("scope-bar").innerText()).replace(/\n/g, " ")
    const layer = (await page.locator(`[data-phone-layer="${b.extraction_id}"]`).innerText()).replace(/\n/g, " ")
    rows.push({ phone: b.label, mapAlone: alone.positioned, mapLayerCount: b.positioned, convOldScreen: old.slice(-120), convNewScreenAloneOn: nw.slice(-120), convLayerCount: layer })
    console.log(JSON.stringify(rows.at(-1)))
  }
} finally { await browser.close() }
