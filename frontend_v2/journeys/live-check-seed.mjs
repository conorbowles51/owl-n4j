#!/usr/bin/env node
// Live walk of the check seed (docs/check-case-seed.md): signed in once with the jobs login over plain http, in the
// synthetic Phones-only case.
//   node journeys/live-check-seed.mjs interview <dossier id> <thread file words> <shots dir>   adds the interview on the dossier, linking the thread
//   node journeys/live-check-seed.mjs draft <phone id> <dossier id> <shots dir>   drafts from it in Draft with AI, adds the drafts, shows a drafted row, withdraws it
//   node journeys/live-check-seed.mjs routine <phone id> <shots dir>   the routine place on Places over time and in the statement form, as the server gives it
// A drafted row stays the model's reading: this walk never confirms it.
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const [mode, ...rest] = process.argv.slice(2)
const shots = rest[rest.length - 1]
mkdirSync(shots, { recursive: true })
const login = readLogin()
const base = `${login.url}/cases/${CASES.phonesOnly}`
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  page.setDefaultTimeout(120000)
  const failed = []
  const fonts = new Set()
  page.on("response", (r) => {
    if (r.status() >= 400 && /\/(api|basemap)\//.test(r.url())) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`)
    if (r.url().includes("/assets/fonts/")) fonts.add(`${r.status()} ${decodeURIComponent(new URL(r.url()).pathname.split("/assets/fonts/")[1])}`)
  })
  const go = async (path) => {
    await page.goto(`${base}${path}`, { waitUntil: "domcontentloaded" })
    if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  }
  if (mode === "interview") {
    const [dossier, words] = rest
    await go(`/dossiers?dossier=${dossier}`)
    await page.getByRole("tab", { name: "Interviews" }).click()
    await page.getByRole("button", { name: "Interview", exact: true }).click()
    const dialog = page.getByRole("dialog", { name: /interview or statement/i })
    await dialog.getByLabel("Date precision").selectOption("day")
    await dialog.locator("#interview-date").fill("2024-06-12")
    await dialog.getByLabel("Working notes").fill("Synthetic check seed: the statement is the linked conversation, with no real case material.")
    await dialog.getByLabel("Search evidence").fill(words)
    await dialog.getByRole("button", { name: "Add", exact: true }).first().click()
    await dialog.getByRole("button", { name: "Remove" }).first().waitFor()
    await page.screenshot({ path: `${shots}/interview-dialog.png`, fullPage: true })
    await dialog.getByRole("button", { name: "Add interview", exact: true }).click()
    await dialog.waitFor({ state: "detached" })
    await page.waitForTimeout(1500)
    await page.screenshot({ path: `${shots}/interview-added.png`, fullPage: true })
  } else if (mode === "draft") {
    const [phone, dossier] = rest
    await go(`/phone-patterns?view=check&subject=e:${phone}`)
    const panel = page.getByRole("region", { name: "Statement check" })
    await panel.waitFor()
    const box = panel.locator("details", { hasText: "Draft with AI" }).first()
    await box.locator("summary").click()
    await box.getByLabel("The person whose statement it is").selectOption(dossier)
    const interview = box.getByRole("checkbox", { name: /2024-06-12/ }).first()
    await interview.check()
    const t0 = Date.now()
    await box.getByRole("button", { name: "Draft with AI" }).click()
    const heading = box.getByText(/^Drafted by .*, not confirmed \(\d+\)/)
    await heading.or(box.getByRole("alert")).first().waitFor({ timeout: 300000 })
    console.log("DRAFT", ((Date.now() - t0) / 1000).toFixed(0), "s", (await heading.or(box.getByRole("alert")).first().textContent())?.slice(0, 240))
    console.log("CLAIMS", JSON.stringify(await box.getByRole("listitem").allTextContents()).slice(0, 1800))
    await page.screenshot({ path: `${shots}/draft-claims.png`, fullPage: true })
    await box.getByRole("button", { name: "Add these drafts" }).click()
    await box.getByText(/drafted claims? added/).waitFor()
    const row = panel.locator("li", { hasText: "Drafted by" }).first()
    await row.waitFor()
    console.log("ROW", (await row.textContent())?.replace(/\s+/g, " ").slice(0, 420))
    await row.scrollIntoViewIfNeeded()
    await page.screenshot({ path: `${shots}/drafted-row-not-confirmed.png`, fullPage: true })
  } else {
    const [phone] = rest
    await go(`/phone-patterns?view=places&subject=e:${phone}`)
    const list = page.getByRole("region", { name: "Routine places" })
    await list.waitFor()
    await list.getByText(/^Routine places \(\d/).waitFor()
    // The map paints late on a loaded box, and a name asks for its font only once it is drawn: no font asked for proves nothing.
    const until = Date.now() + 180000
    while (Date.now() < until && ![...fonts].some((f) => f.includes("Noto Sans Medium"))) await page.waitForTimeout(2000)
    await page.waitForTimeout(5000)
    console.log("FONT_REQUESTS", JSON.stringify([...fonts]))
    if (![...fonts].some((f) => f.startsWith("200 ") && f.includes("Noto Sans Medium"))) failed.push("no Noto Sans Medium font was asked for: the place name was not drawn")
    console.log("ROUTINE", (await list.textContent())?.replace(/\s+/g, " ").slice(0, 420))
    await page.screenshot({ path: `${shots}/routine-place-list.png`, fullPage: true })
    await go(`/phone-patterns?view=check&subject=e:${phone}`)
    const panel = page.getByRole("region", { name: "Statement check" })
    await panel.waitFor()
    const form = panel.locator("details", { hasText: "Enter a statement" }).first()
    await form.locator("summary").click()
    await form.getByLabel("What the statement says").selectOption("at_place")
    const pick = form.getByLabel("A routine place of this phone or person")
    await pick.locator("option").nth(1).waitFor({ state: "attached" })
    console.log("ROUTINE OPTIONS", (await pick.locator("option").count()) - 1, (await pick.locator("option").nth(1).textContent())?.slice(0, 120))
    await page.screenshot({ path: `${shots}/routine-place-in-form.png`, fullPage: true })
  }
  console.log("FAILED_REQUESTS", JSON.stringify(failed))
  if (failed.length) process.exitCode = 1
} finally {
  await browser.close()
}
