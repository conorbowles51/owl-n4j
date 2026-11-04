#!/usr/bin/env node
// cb-coloc-rest live check: Together between the two synthetic Bluetooth phones in the phones-only synthetic case,
// signed in once with the jobs login over plain http. Prints the evidence lines; screenshots the Together section.
//   node journeys/live-coloc-check.mjs <phone A id> <phone B id> <shots dir>
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const [a, b, shots] = process.argv.slice(2)
mkdirSync(shots, { recursive: true })
const login = readLogin()
const browser = await chromium.launch()
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  await page.goto(`${login.url}/cases/${CASES.phonesOnly}/phone-patterns?view=together&subject=e:${a}`, { waitUntil: "domcontentloaded" })
  console.log("isSecureContext", await page.evaluate(() => window.isSecureContext))
  const section = page.getByRole("region", { name: "Together" })
  await section.waitFor({ timeout: 120000 })
  await section.locator("#together-other").selectOption(b)
  await section.getByRole("button", { name: "Compare the last week" }).click()
  const list = section.getByRole("list", { name: "Kinds of evidence" })
  await list.waitFor({ timeout: 180000 })
  for (const li of await list.getByRole("listitem").allTextContents()) console.log("EVIDENCE", li)
  console.log("SUMMARY", (await section.locator("p").first().textContent())?.slice(0, 200))
  await section.screenshot({ path: `${shots}/together-bluetooth.png` })
  await page.goto(`${login.url}/cases/${CASES.phonesOnly}/phone-patterns?view=places&subject=e:${a}`, { waitUntil: "domcontentloaded" })
  const places = page.getByRole("region", { name: "Places over time" })
  await places.waitFor({ timeout: 120000 })
  await page.waitForTimeout(4000)
  console.log("PLACES", (await places.locator("p").first().textContent())?.slice(0, 400))
  await places.screenshot({ path: `${shots}/places-sim-country-code.png` })
} finally {
  await browser.close()
}
