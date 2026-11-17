#!/usr/bin/env node
// Phone layer control present on the screens built last (lx-phonelayers G), demo case, read only:
//   node journeys/live-phonelayers-screens.mjs --shots <dir>
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"
const i = process.argv.indexOf("--shots"); const shots = process.argv[i + 1]; mkdirSync(shots, { recursive: true })
const login = readLogin(); const C = CASES.demo
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage(); await page.setViewportSize({ width: 1500, height: 900 })
  const errors = []; page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)))
  const pg = await page.goto(`${login.url}/cases/${C}/phones`, { waitUntil: "domcontentloaded" })
  const phones = await page.evaluate(async (c) => (await (await fetch(`/api/phones?case_id=${c}`)).json()).phones.map((p) => p.extraction_id), C)
  const screens = [
    ["media", `phones/${phones[0]}/records/media`], ["money", "phone-money"], ["monitoring", "phone-analyses/monitoring-apps"],
    ["incident", "phone-analyses/incident-window"], ["relationships", "phone-analyses/relationships"], ["patterns", "phone-patterns"],
  ]
  for (const [name, path] of screens) {
    await page.goto(`${login.url}/cases/${C}/${path}${path.includes("?") ? "&" : "?"}phone_layers=on`, { waitUntil: "domcontentloaded" })
    const found = await page.waitForSelector("[data-testid=phone-layers]", { timeout: 60000 }).then(() => true).catch(() => false)
    const text = found ? (await page.locator("[data-testid=phone-layers]").first().innerText()).replace(/\n/g, " | ").slice(0, 200) : ""
    console.log(name, JSON.stringify({ control: found, text }))
    await page.screenshot({ path: `${shots}/demo-1500-screen-${name}.png`, timeout: 120000 }).catch(() => {})
  }
  // Add other phones on a per-phone page
  await page.goto(`${login.url}/cases/${C}/phones/${phones[0]}?phone_layers=on`, { waitUntil: "domcontentloaded" })
  await page.getByRole("heading", { name: /Phone summary/ }).waitFor({ timeout: 120000 }).catch(() => {})
  const add = await page.getByTestId("add-other-phones").waitFor({ timeout: 30000 }).then(() => true).catch(() => false)
  console.log("phone summary add other phones", add)
  console.log("page errors", errors.length, JSON.stringify(errors.slice(0, 3)))
} finally { await browser.close() }
