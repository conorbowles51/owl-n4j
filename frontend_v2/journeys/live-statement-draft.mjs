#!/usr/bin/env node
// cb-statements-rest live check, second part. Signed in once with the jobs login over plain http.
//   node journeys/live-statement-draft.mjs draft <phone id> <shots dir>   drafts from the phones-only case's interview, settles one draft, confirms it
//   node journeys/live-statement-draft.mjs places <case id> <phone A> <phone B> <shots dir>   a routine place, and Together with two sets of allowances
// Every statement it makes is withdrawn at the end.
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const [mode, ...rest] = process.argv.slice(2)
const shots = rest[rest.length - 1]
mkdirSync(shots, { recursive: true })
const login = readLogin()
const browser = await chromium.launch()
const withdraw = (page, k, test) => page.evaluate(async ([kase, source]) => {
  const items = (await (await fetch(`/api/pattern/${kase}/claims`)).json()).items.filter((c) => c.status !== "withdrawn" && new RegExp(source).test(JSON.stringify([c.window_text, c.source_anchor, c.ai_model])))
  for (const c of items) await fetch(`/api/pattern/${kase}/claims/${c.id}/withdraw`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Live check, withdrawn by the check itself." }) })
  return items.length
}, [k, test])
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  page.setDefaultTimeout(180000)
  const failed = []
  page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`) })
  if (mode === "draft") {
    const [phone] = rest
    await page.goto(`${login.url}/cases/${CASES.phonesOnly}/phone-patterns?view=check&subject=e:${phone}`, { waitUntil: "domcontentloaded" })
    const panel = page.getByRole("region", { name: "Statement check" })
    await panel.waitFor()
    const box = panel.locator("details", { hasText: "Draft with AI" }).first()
    await box.locator("summary").click()
    const who = box.getByLabel("The person whose statement it is")
    await who.locator("option").nth(1).waitFor({ state: "attached" })
    // the check cases hold no document with text, so the model reads a synthetic conversation, through the same route
    const dossiers = (await who.locator("option").evaluateAll((o) => o.map((x) => x.value))).filter(Boolean).slice(0, 4)
    let drafted = 0
    for (const dossier of dossiers) {
      drafted = await page.evaluate(async ([k, d, t, e]) => {
      const post = async (u, b) => { const r = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b ?? {}) }); if (!r.ok) throw new Error(`${r.status} ${await r.text()}`); return r.json() }
      const out = await post(`/api/pattern/${k}/claim-drafts`, { dossier_id: d, conversation_locator: t, subject: { kind: "extraction", extraction_id: e } })
      for (let i = 0; i < 120; i++) {
        const o = await (await fetch(`/api/workspace/${k}/ai-outputs/${out.id}`)).json()
        if (o.job_status === "failed" || o.job_status === "cancelled") throw new Error(`drafting ${o.job_status}`)
        if (o.job_status === "completed") { await post(`/api/workspace/${k}/ai-outputs/${out.id}/accept`); return (o.content.claims || []).length }
        await new Promise((ok) => setTimeout(ok, 3000))
      }
      throw new Error("drafting still running")
      }, [CASES.phonesOnly, dossier, process.env.THREAD, phone])
      console.log("DRAFTS ADDED", drafted)
      if (drafted) break
    }
    if (!drafted) throw new Error("the model found no statement to draft in this conversation")
    await page.reload({ waitUntil: "domcontentloaded" })
    await panel.waitFor()
    const row = panel.locator("li", { has: page.getByRole("button", { name: "Fill these in" }) }).first()
    await row.waitFor()
    console.log("DRAFT ROW", (await row.textContent())?.slice(0, 420))
    await page.screenshot({ path: `${shots}/draft-before-settling.png`, fullPage: true })
    await row.getByRole("button", { name: "Fill these in" }).click()
    await row.getByLabel("From (UTC)").fill("2023-12-05T20:00")
    await row.getByLabel("Until (UTC)").fill("2023-12-06T07:00")
    await row.getByLabel("Zone the statement uses").fill("UTC")
    if (await row.getByLabel("Latitude").count()) { await row.getByLabel("Latitude").fill("40.7"); await row.getByLabel("Longitude").fill("-74") }
    const other = row.getByLabel(/^The other (phone or )?person/)
    if (await other.count()) { await other.locator("option").nth(1).waitFor({ state: "attached" }); await other.selectOption({ index: 1 }) }
    await row.getByRole("button", { name: "Save changes" }).click()
    await row.getByRole("button", { name: "Confirm" }).click()
    await row.getByText("Confirmed", { exact: true }).waitFor()
    console.log("DRAFT CONFIRMED", (await row.textContent())?.slice(0, 420))
    await page.screenshot({ path: `${shots}/draft-confirmed-model-words-kept.png`, fullPage: true })
    console.log("WITHDRAWN", await withdraw(page, CASES.phonesOnly, "\"quote\""))
  } else {
    const [kase, a, b] = rest
    // no live phone has a routine place (0 of 14), so the list alone is supplied here; saving and confirming are real
    await page.route(/\/routine\?/, (r) => r.fulfill({ json: { places: [{ cluster_id: 1, lat: 40.7128, lon: -74.006, radius_m: 80, stay_count: 40, day_count: 21, routine: true,
      label: "Check place (supplied by this check)", place_id: null, label_by: null, first_utc: "2024-01-01T00:00:00Z", last_utc: "2024-02-01T00:00:00Z" }], routine_places: [1] } }))
    await page.goto(`${login.url}/cases/${kase}/phone-patterns?view=check&subject=e:${a}`, { waitUntil: "domcontentloaded" })
    const panel = page.getByRole("region", { name: "Statement check" })
    await panel.waitFor()
    const form = panel.locator("details", { hasText: "Enter a statement" }).first()
    await form.locator("summary").click()
    await form.getByLabel("What the statement says").selectOption("at_place")
    const pick = form.getByLabel("A routine place of this phone or person")
    await page.waitForTimeout(8000)
    const options = await pick.locator("option").allTextContents()
    console.log("ROUTINE OPTIONS", options.length - 1, options.slice(1, 4).join(" / "))
    if (options.length > 1) {
      const words = `live check ${Date.now()} at the usual place`
      await form.getByLabel("The statement's own words").fill(words)
      await form.getByLabel("From (UTC)").fill("2024-10-10T00:00")
      await form.getByLabel("Until (UTC)").fill("2024-10-11T00:00")
      await pick.selectOption({ index: 1 })
      await form.getByRole("button", { name: "Save as not confirmed" }).click()
      const row = panel.locator("li", { hasText: words }).first()
      await row.getByRole("button", { name: "Confirm" }).click()
      await row.getByText("Confirmed", { exact: true }).waitFor()
      console.log("ROUTINE CONFIRMED", (await row.locator("p").first().textContent())?.slice(0, 200))
      await page.screenshot({ path: `${shots}/statement-routine-place.png`, fullPage: true })
      console.log("WITHDRAWN", await withdraw(page, kase, "^\\[\"live check"))
    }
    await page.goto(`${login.url}/cases/${kase}/phone-patterns?view=together&subject=e:${a}`, { waitUntil: "domcontentloaded" })
    const together = page.getByRole("region", { name: "Together" })
    await together.waitFor()
    await together.locator("#together-other").selectOption(`e:${b}`)
    const summary = together.locator("p", { hasText: "pairs compared" })
    for (const [radius, kmh] of [["1000", "144"], ["5000", "900"]]) {
      await together.getByLabel(/Radius to assume/).fill(radius)
      await together.getByLabel(/Fastest travel/).fill(kmh)
      await together.getByRole("button", { name: /^Compare / }).click()
      await page.waitForTimeout(500)
      await together.getByText(new RegExp(`radius of ${Number(radius).toLocaleString("en-US")} m`)).waitFor({ timeout: 180000 })
      console.log("TOGETHER", (await summary.textContent())?.slice(0, 260))
    }
    await together.screenshot({ path: `${shots}/together-reference-allowances.png` })
  }
  console.log("FAILED_REQUESTS", JSON.stringify(failed))
} finally {
  await browser.close()
}
