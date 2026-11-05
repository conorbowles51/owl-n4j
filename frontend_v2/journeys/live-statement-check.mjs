#!/usr/bin/env node
// cb-statements-rest live check: every kind of statement reaches Confirm through the form, a statement missing its
// window is settled through "Fill these in", and Together runs with its own radius and speed. Signed in once with the
// jobs login over plain http, in the phones-only synthetic case. The statements it makes are withdrawn at the end.
//   node journeys/live-statement-check.mjs <phone A id> <phone B id> <shots dir>
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const [a, b, shots] = process.argv.slice(2)
mkdirSync(shots, { recursive: true })
const login = readLogin()
const browser = await chromium.launch()
const tag = `live check ${Date.now()}`
const made = []
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  page.setDefaultTimeout(120000)
  const failed = []
  page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`) })
  page.on("pageerror", (e) => failed.push(`pageerror ${String(e).slice(0, 200)}`))
  await page.goto(`${login.url}/cases/${CASES.phonesOnly}/phone-patterns?view=check&subject=e:${a}`, { waitUntil: "domcontentloaded" })
  console.log("isSecureContext", await page.evaluate(() => window.isSecureContext))
  const panel = page.getByRole("region", { name: "Statement check" })
  await panel.waitFor()
  const form = panel.locator("details", { hasText: "Enter a statement" }).first()
  await form.locator("summary").click()
  const dt = (name, v) => form.getByLabel(name).fill(v)
  async function choose(label, pick) {
    const select = form.getByLabel(label)
    await select.locator("option").nth(1).waitFor({ state: "attached" })
    await select.selectOption(pick ?? { index: 1 })
    return (await select.locator("option:checked").textContent())?.slice(0, 80)
  }
  for (const [kind, words] of [["inactive", "asleep by about eleven"], ["active", "on the phone"], ["at_place", "at home"], ["not_at_place", "not at home"],
    ["with_subject", "with them"], ["apart_from_subject", "apart from them"], ["contact", "spoke to them"], ["no_contact", "no contact"]]) {
    await form.getByLabel("What the statement says").selectOption(kind)
    const text = `${tag} ${words}`
    await form.getByLabel("The statement's own words").fill(text)
    await dt("From (UTC)", "2023-03-14T23:00")
    await dt("Until (UTC)", "2023-03-15T07:00")
    let picked = ""
    if (kind === "inactive") { await form.getByLabel(/Minutes of use to allow/).fill("10"); picked = "10 minutes" }
    if (kind.endsWith("place")) picked = await choose("A routine place of this phone or person").catch(async () => {
      await form.getByLabel("Latitude").fill("40.7"); await form.getByLabel("Longitude").fill("-74"); return "typed point (no routine place)"
    })
    if (kind.endsWith("subject")) picked = await choose("The other phone or person", JSON.stringify({ kind: "extraction", extraction_id: b }))
    if (kind.endsWith("contact")) {
      await form.getByLabel("Find a name or number").fill("")
      await form.getByRole("button", { name: "Find", exact: true }).click()
      const first = form.locator("li button").first()
      await first.waitFor()
      picked = `${await form.getByText(/found/).first().textContent()} -> ${(await first.textContent())?.slice(0, 12)}…`
      await first.click()
    }
    await form.getByRole("button", { name: "Save as not confirmed" }).click()
    const row = panel.locator("li", { hasText: text }).first()
    await row.getByRole("button", { name: "Confirm" }).click()
    await row.getByText("Confirmed", { exact: true }).waitFor()
    console.log("CONFIRMED", kind, "|", picked, "|", (await row.locator("p").first().textContent())?.slice(0, 120))
  }
  await panel.screenshot({ path: `${shots}/statements-every-kind.png` })

  // settle: a statement saved with no window and no place names what is missing and fills it through the editor
  await form.getByLabel("What the statement says").selectOption("at_place")
  await form.getByLabel("The statement's own words").fill(`${tag} at the flat`)
  await dt("From (UTC)", "")
  await dt("Until (UTC)", "")
  await form.getByRole("button", { name: "Save as not confirmed" }).click()
  const row = panel.locator("li", { hasText: `${tag} at the flat` }).first()
  console.log("SETTLE", await row.getByText(/Settle before confirming/).textContent())
  await page.screenshot({ path: `${shots}/settle-before-confirming.png` })
  await row.getByRole("button", { name: "Fill these in" }).click()
  await row.getByLabel("From (UTC)").fill("2023-03-14T18:00")
  await row.getByLabel("Until (UTC)").fill("2023-03-14T22:00")
  await row.getByLabel("Latitude").fill("40.7")
  await row.getByLabel("Longitude").fill("-74")
  await row.getByRole("button", { name: "Save changes" }).click()
  await row.getByRole("button", { name: "Confirm" }).click()
  await row.getByText("Confirmed", { exact: true }).waitFor()
  console.log("SETTLED", (await row.locator("p").first().textContent())?.slice(0, 160))
  await page.screenshot({ path: `${shots}/settled-and-confirmed.png`, fullPage: true })

  await page.goto(`${login.url}/cases/${CASES.phonesOnly}/phone-patterns?view=together&subject=e:${a}`, { waitUntil: "domcontentloaded" })
  const together = page.getByRole("region", { name: "Together" })
  await together.waitFor()
  await together.locator("#together-other").selectOption(`e:${b}`)
  await together.getByLabel(/Radius to assume/).fill("2500")
  await together.getByRole("button", { name: /Allow for air travel/ }).click()
  await together.getByRole("button", { name: /^Compare / }).click()
  const words = together.getByText(/assumed radius of 2,500 m/)
  await words.waitFor({ timeout: 180000 })
  console.log("TOGETHER", (await words.textContent())?.slice(0, 300))
  await together.screenshot({ path: `${shots}/together-allowances.png` })

  const token = await page.evaluate(() => localStorage.getItem("token") ?? localStorage.getItem("auth_token"))
  const list = await page.evaluate(async (c) => (await (await fetch(`/api/pattern/${c}/claims`)).json()).items, CASES.phonesOnly)
  for (const c of list.filter((x) => (x.window_text || "").startsWith(tag))) {
    made.push(c.id)
    await page.evaluate(async ([k, id, t]) => {
      const r = await fetch(`/api/pattern/${k}/claims/${id}/withdraw`, { method: "POST", headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) }, body: JSON.stringify({ reason: "Live check, withdrawn by the check itself." }) })
      if (!r.ok) throw new Error(`withdraw ${r.status}`)
    }, [CASES.phonesOnly, c.id, token])
  }
  console.log("WITHDRAWN", made.length)
  console.log("FAILED_REQUESTS", JSON.stringify(failed))
} finally {
  await browser.close()
}
