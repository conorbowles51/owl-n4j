#!/usr/bin/env node
// Live check of three phone readings, signed in once with the jobs login over plain http, in the synthetic cases only:
// an Email's direction in Conversations, a Harvested point's label on Places over time, and a Graph pair's count
// against what Conversations shows for that pair. Reads and screenshots only; nothing is written.
//   node journeys/live-readcarry.mjs --shots <dir> --harvested-phone <extraction id> [--phones-case phonesOnly] [--graph-case training]
import { mkdirSync } from "node:fs"
import { join } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const shots = arg("shots")
if (!shots || !arg("harvested-phone")) {
  console.error("usage: --shots <dir> --harvested-phone <extraction id>")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const phonesCase = CASES[arg("phones-case", "phonesOnly")]
const graphCase = CASES[arg("graph-case", "training")]
const login = readLogin()
const browser = await chromium.launch({ timeout: 600000 })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
// the shared sign-in's 30 s runs out on a loaded box before the login page has drawn
page.setDefaultTimeout(240000)
page.setDefaultNavigationTimeout(240000)
await page.goto(`${login.url}/login`, { waitUntil: "domcontentloaded" })
await page.getByPlaceholder("Enter your username").fill(login.email)
await page.getByPlaceholder("Enter your password").fill(login.password)
await page.getByRole("button", { name: /sign in/i }).click()
await page.waitForURL((u) => !u.pathname.startsWith("/login"))
const failed = []
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? `: ${detail}` : ""}`)
  if (!ok) failed.push(name)
}
const go = async (caseId, path) => {
  await page.goto(`${login.url}/cases/${caseId}${path}`, { waitUntil: "domcontentloaded" })
  check("plain http", (await page.evaluate(() => window.isSecureContext)) === false)
}
const shot = (name) => page.screenshot({ path: join(shots, `${name}.png`) })

// Email direction: each filter's count line, and where the mails with the owner marked on To sit.
const counts = {}
for (const dir of ["incoming", "outgoing", "unknown"]) {
  await go(phonesCase, `/conversations?kinds=email&directions=${dir}`)
  const line = page.getByText(/[\d,]+ messages? and calls? match|No messages/).first()
  await line.waitFor()
  await page.waitForTimeout(3000)
  const owner = await page.getByText(/^sender\d@example\.test$/).count()
  counts[dir] = owner
  console.log(`email ${dir}: ${await line.innerText()} ; ${owner} threads from the owner-marked mails`)
  await shot(`email-${dir}`)
}
check("Owner-marked mails read Incoming", counts.incoming === 3 && counts.outgoing === 0 && counts.unknown === 0, JSON.stringify(counts))

// Harvested: the note under the map and the row's label, on whichever phone holds them.
let heard = false
{
  await go(phonesCase, `/phone-patterns?view=places&subject=e:${arg("harvested-phone")}`)
  // the builder's points fall in this window, well before the view's default last week
  await page.locator("#places-from").fill("2023-11-01")
  await page.locator("#places-to").fill("2024-05-01")
  const positions = page.getByText(/The positions \([\d,]+ listed\)/)
  await positions.waitFor({ timeout: 60000 }).catch(() => {})
  await page.waitForTimeout(3000)
  const note = page.getByText(/dots? (is|are) (the )?positions? of (a )?networks? or towers?/)
  if (!(await note.count())) throw new Error(`no Harvested note: ${await positions.innerText().catch(() => "no list")}`)
  heard = true
  console.log(`harvested note: ${(await note.first().innerText()).slice(0, 260)}`)
  await positions.click()
  const label = page.getByText("A network or tower the phone heard, not the phone's position")
  await label.first().waitFor({ timeout: 30000 })
  check("Harvested row label", (await label.count()) === 6, `${await label.count()} rows`)
  await label.first().scrollIntoViewIfNeeded()
  await shot("harvested-label")
}
check("The phone shows Harvested positions", heard)

// Graph pair against Conversations: the edge's button and the list it opens.
await go(graphCase, "/graph")
const section = page.getByRole("region", { name: "Messages and calls between people" })
await section.waitFor({ timeout: 120000 })
const pair = section.getByRole("button", { name: /^[\d,]+ messages?/ }).first()
await pair.waitFor({ timeout: 60000 })
const words = await pair.innerText()
console.log(`graph pair: ${words}`)
const n = Number(words.match(/^([\d,]+)/)[1].replace(/,/g, ""))
await section.screenshot({ path: join(shots, "graph-pair.png") })
await pair.click()
await page.waitForURL(/conversations/, { timeout: 30000 })
await page.waitForTimeout(5000)
await shot("graph-pair-conversations")
const body = await page.locator("body").innerText()
const shown = body.match(/([\d,]+) (messages?|records?|rows?|items?)\b/g) ?? []
console.log(`conversations counts: ${[...new Set(shown)].slice(0, 8).join(" | ")}`)
check("Conversations shows the pair's message count", shown.some((s) => Number(s.match(/^[\d,]+/)[0].replace(/,/g, "")) === n), `${n}`)

await browser.close()
console.log(failed.length ? `FAILED: ${failed.join("; ")}` : "ALL PASS")
process.exit(failed.length ? 1 : 0)
