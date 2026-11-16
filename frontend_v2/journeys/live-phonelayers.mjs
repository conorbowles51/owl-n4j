#!/usr/bin/env node
// Phone layers on the live site (lx-phonelayers G): Map, Conversations and Timeline with several phones on, read only.
//   node journeys/live-phonelayers.mjs --case demo|ref1 --shots <dir> --out <file.json> [--width 1500]
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
const step = (name, data) => { res.steps.push({ name, ...data }); console.log(name, JSON.stringify(data).slice(0, 300)) }
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  await page.setViewportSize({ width, height: width > 800 ? 900 : 844 })
  const errors = []
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)) })
  page.on("pageerror", (e) => errors.push(`pageerror ${String(e.message).slice(0, 200)}`))
  const base = login.url
  const shot = (n) => page.screenshot({ path: `${shots}/${which}-${width}-${n}.png`, timeout: 120000 }).catch((e) => console.log("shot failed", n, String(e).slice(0, 80)))
  const post = (path, body) => page.evaluate(async ([p, b]) => (await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json(), [path, body])
  await page.goto(`${base}/cases/${C}/map?phone_layers=on`, { waitUntil: "domcontentloaded" })
  await page.waitForSelector("[data-testid=phone-layers]", { timeout: 60000 }).catch(() => {})
  const sum = await post("/api/phones/map/summary", { case_id: C, filter: {} })
  step("summary all phones", { positioned: sum.positioned, by_phone: sum.by_phone?.map((b) => [b.label, b.positioned]) })
  const layers = page.locator("[data-testid=phone-layers]")
  step("control shown", { present: await layers.count(), text: (await layers.innerText().catch(() => "")).replace(/\n/g, " | ") })
  await shot("map-all")
  // trajectory on, timed on the real path
  const t0 = Date.now()
  await page.getByLabel("Show routes").click().catch(() => {})
  await page.getByText(/moves? drawn/).waitFor({ timeout: 120000 }).catch(() => {})
  const routeBar = await page.getByTestId("route-bar").innerText().catch(() => "")
  step("routes on", { ms: Date.now() - t0, bar: routeBar.replace(/\n/g, " ") })
  await page.waitForTimeout(2500)
  await shot("map-routes")
  // switch one phone off (the one with most positions among ≥2 that have any)
  const withPos = (sum.by_phone ?? []).filter((b) => b.positioned > 0).sort((a, b) => b.positioned - a.positioned)
  if (withPos.length >= 2) {
    const off = withPos[0]
    await page.locator(`[data-phone-layer="${off.extraction_id}"] input[type=checkbox]`).click()
    await page.waitForTimeout(3000)
    const after = await post("/api/phones/map/summary", { case_id: C, filter: { phones: (sum.by_phone).map((b) => b.extraction_id).filter((x) => x !== off.extraction_id) } })
    const bar2 = await page.getByTestId("route-bar").innerText().catch(() => "")
    const status = await page.locator("[data-testid=phone-layers]").innerText()
    step("one phone off", { off: off.label, positionedBefore: sum.positioned, positionedAfter: after.positioned, offStillCounts: off.positioned, status: status.replace(/\n/g, " | "), routeBar: bar2.replace(/\n/g, " "), url: page.url().replace(base, "") })
    await shot("map-one-off")
    await page.reload({ waitUntil: "domcontentloaded" })
    await page.waitForSelector("[data-testid=phone-layers]", { timeout: 60000 })
    const checked = await page.locator("[data-testid=phone-layers] input[type=checkbox]").evaluateAll((els) => els.map((e) => e.checked))
    step("after reload the choice stays", { checked })
  }
  if (which === "demo") {
    for (const [name, path, noun] of [["conversations", "conversations", "messages"], ["timeline", "timeline", "entries"]]) {
      await page.goto(`${base}/cases/${C}/${path}?phone_layers=on`, { waitUntil: "domcontentloaded" })
      if (name === "timeline") await page.getByRole("button", { name: /^Phones \(/ }).click({ timeout: 30000 }).catch(() => {})
      await page.waitForSelector("[data-testid=phone-layers]", { timeout: 60000 }).catch(() => {})
      await page.waitForTimeout(5000)
      const txt = await page.locator("[data-testid=phone-layers]").innerText().catch(() => "")
      step(`${name} control`, { text: txt.replace(/\n/g, " | ") })
      const first = page.locator("[data-testid=phone-layers] input[type=checkbox]").nth(2)
      if (await first.count()) { await first.click({ timeout: 10000 }).catch(() => {}); await page.waitForTimeout(5000) }
      const txt2 = await page.locator("[data-testid=phone-layers]").innerText().catch(() => "")
      step(`${name} third phone off`, { text: txt2.replace(/\n/g, " | "), url: page.url().replace(base, "") })
      await shot(name)
    }
  }
  step("console errors", { n: errors.length, errors: errors.slice(0, 5) })
} finally {
  writeFileSync(out, JSON.stringify(res, null, 2))
  await browser.close()
}
