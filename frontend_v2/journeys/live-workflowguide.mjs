#!/usr/bin/env node
// Live check of the Guide's Workflows section (lx-workflowguide G), signed in with the jobs login over plain http.
// Read only: a request that is not a GET is stopped and reported, except the app's own view records.
//
//   node journeys/live-workflowguide.mjs --out <dir> [--width 1440|390] [--follow money,contact,theory] [--ends]
//
// Opens the Workflows list from the Guide menu on the demo case, follows each --follow workflow step by step with
// Next (and the arrow keys), presses Open this screen on every step and checks the marked control is found, and with
// --ends opens every workflow's first and last step. Every picture on a step must load. Screenshots go to --out.
import { mkdirSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const out = arg("out")
if (!out) throw new Error("--out <dir> is required")
mkdirSync(out, { recursive: true })
const widths = arg("width") ? [Number(arg("width"))] : [1440, 390]
const follow = (arg("follow", "") || "").split(",").filter(Boolean)
const ends = process.argv.includes("--ends")
const quiet = process.argv.includes("--quiet")
const C = CASES.demo
const VIEW_POSTS = [/\/api\/investigation-trail/, /\/api\/trail/, /\/api\/auth\/refresh/, /\/api\/history\/cases\/[^/]+$/,
  /\/api\/request-speed\/page-views$/, /\/api\/evidence\/route-check$/, /\/api\/activity\/files$/, /\/api\/phones\//,
  /\/api\/citations\/resolve$/, /\/api\/workspace\/[^/]+\/financial-evidence-changes$/]

const login = readLogin()
const browser = await chromium.launch()
const report = { checks: [], failed: [], stopped: [], brokenImages: [] }
const ok = (what) => report.checks.push(what)
const bad = (what) => { report.failed.push(what); console.log("FAILED", what) }

async function openList(page, base) {
  await page.goto(`${base}/cases/${C}/financial?view=overview`, { waitUntil: "domcontentloaded" })
  await page.getByText("Money in this scope").first().waitFor({ timeout: 120_000 })
  await page.locator('[data-guide="guide-menu"]').first().click()
  await page.locator('[data-guide="guide-workflows"]').first().click()
  await page.getByTestId("workflow-guide").waitFor({ timeout: 30_000 })
}

async function imagesLoaded(page, where) {
  const pics = page.getByTestId("workflow-guide").locator("img")
  const n = await pics.count()
  for (let i = 0; i < n; i++) {
    const img = pics.nth(i)
    await img.scrollIntoViewIfNeeded().catch(() => {})
    const loaded = await img.evaluate(async (e) => {
      if (!e.complete) await new Promise((r) => { e.onload = r; e.onerror = r; setTimeout(r, 30_000) })
      return e.naturalWidth > 0
    })
    const alt = await img.getAttribute("alt")
    if (!loaded) report.brokenImages.push(`${where}: ${await img.evaluate((e) => e.currentSrc)}`)
    if (!alt) bad(`${where}: picture with no alt text`)
  }
  return n
}

/** "Step 3 of 9" as written (the screen shows it in capitals). */
async function stepCount(page) {
  return (await page.getByTestId("workflow-tutorial").getByText(/^Step \d+ of \d+$/i).first().textContent()).trim()
}

/** A workflow's card on the list: by its id, or by its title on a build without card ids. */
function card(page, id) {
  const byId = page.getByTestId("workflow-guide").locator(`[data-workflow-id="${id}"]`)
  return TITLES[id] ? byId.or(page.getByTestId("workflow-guide").getByRole("button", { name: TITLES[id] })).first() : byId.first()
}
const TITLES = { money: "Where did the money go?" }

async function stepTitle(page) {
  return (await page.getByTestId("workflow-tutorial").locator("h3, [data-step-title]").first().innerText()).trim()
}

try {
  const { context: first } = await signIn(browser, login)
  const state = await first.storageState()
  await first.close()
  for (const width of widths) {
    const phone = width < 640
    const context = await browser.newContext({
      viewport: { width, height: phone ? 844 : 900 }, deviceScaleFactor: phone ? 2 : 1, storageState: state,
    })
    const page = await context.newPage()
    await page.route("**/api/**", (r) => {
      const q = r.request()
      const path = new URL(q.url()).pathname
      if (["GET", "HEAD", "OPTIONS"].includes(q.method()) || VIEW_POSTS.some((p) => p.test(path))) return r.continue()
      report.stopped.push(`${q.method()} ${path}`)
      return r.abort()
    })
    const base = login.url
    await openList(page, base)
    await page.waitForTimeout(800)
    await page.screenshot({ path: join(out, `list-${width}.png`) })
    const status = await page.getByRole("status").filter({ hasText: /workflows/ }).first().innerText().catch(() => "")
    ok(`${width}: list says "${status}"`)
    await page.getByLabel("Find a workflow").fill("money")
    await page.waitForTimeout(500)
    await page.screenshot({ path: join(out, `list-search-${width}.png`) })
    ok(`${width}: search "money" says "${await page.getByRole("status").filter({ hasText: /workflows/ }).first().innerText().catch(() => "")}"`)
    await page.getByLabel("Find a workflow").fill("")
    await page.getByRole("button", { name: "By kind of case" }).click()
    await page.waitForTimeout(400)
    await page.screenshot({ path: join(out, `list-kind-${width}.png`) })
    await page.getByRole("button", { name: "By question" }).click()

    const cards = page.getByTestId("workflow-guide").locator("[data-workflow-id]")
    const ids = await cards.evaluateAll((es) => es.map((e) => e.getAttribute("data-workflow-id")))
    ok(`${width}: ${ids.length} workflow cards`)

    for (const id of follow) {
      await card(page, id).click()
      await page.getByTestId("workflow-tutorial").waitFor()
      const count = await stepCount(page)
      const total = Number(count.match(/of (\d+)/)[1])
      for (let s = 1; s <= total; s++) {
        const title = await stepTitle(page)
        await imagesLoaded(page, `${width} ${id} step ${s}`)
        await page.screenshot({ path: join(out, `${id}-${s}-${width}.png`) })
        // Open this screen, see the control marked, come back to the step
        await page.getByRole("link", { name: "Open this screen" }).or(page.getByRole("button", { name: "Open this screen" })).first().click()
        const back = page.getByRole("button", { name: "Back to the step" })
        await back.waitFor({ timeout: 60_000 })
        const ring = page.getByTestId("workflow-ring")
        const found = await ring.waitFor({ timeout: 25_000 }).then(() => true, () => false)
        const missingNote = await page.getByText("The marked control is not on this screen in your case yet.").isVisible().catch(() => false)
        await page.waitForTimeout(600)
        await page.screenshot({ path: join(out, `${id}-${s}-open-${width}.png`) })
        const url = new URL(page.url()).pathname + new URL(page.url()).search
        if (found) ok(`${width} ${id} ${s} "${title}": opened ${url}, control marked`)
        else ok(`${width} ${id} ${s} "${title}": opened ${url}, no control to mark${missingNote ? " (says so)" : ""}`)
        await back.click()
        await page.getByTestId("workflow-tutorial").waitFor()
        const after = await stepTitle(page)
        if (after !== title) bad(`${width} ${id} ${s}: Back to the step came back to "${after}", not "${title}"`)
        if (s < total) {
          if (s % 2) await page.getByRole("button", { name: /^Next/ }).click()
          else { await page.getByTestId("workflow-tutorial").focus(); await page.keyboard.press("ArrowRight") }
          await page.waitForTimeout(300)
          const moved = await stepCount(page)
          if (moved !== `Step ${s + 1} of ${total}`) bad(`${width} ${id}: after step ${s} it says ${moved}`)
        }
      }
      await page.keyboard.press("ArrowLeft")
      await page.waitForTimeout(300)
      const leftTo = await stepCount(page)
      if (total > 1 && leftTo !== `Step ${total - 1} of ${total}`) bad(`${width} ${id}: ArrowLeft from the last step says ${leftTo}`)
      else ok(`${width} ${id}: arrow keys and Next walk all ${total} steps`)
      await page.getByRole("button", { name: "All workflows" }).click()
      await page.getByLabel("Find a workflow").waitFor()
    }

    if (ends) {
      for (const id of ids) {
        await card(page, id).click()
        await page.getByTestId("workflow-tutorial").waitFor()
        const n1 = await imagesLoaded(page, `${width} ${id} first`)
        const count = await stepCount(page)
        const total = Number(count.match(/of (\d+)/)[1])
        // jump to the last step from the step list (the strip on a phone)
        const steps = phone ? page.getByRole("navigation", { name: "Steps" }) : page.getByTestId("workflow-tutorial").getByRole("navigation").last()
        await steps.getByRole("button").nth(total - 1).click()
        await page.waitForTimeout(300)
        const last = await stepCount(page)
        if (last !== `Step ${total} of ${total}`) bad(`${width} ${id}: jump to last says ${last}`)
        const n2 = await imagesLoaded(page, `${width} ${id} last`)
        if (!n1 || !n2) bad(`${width} ${id}: a step with no picture`)
        await page.getByRole("button", { name: "All workflows" }).click()
        await page.getByLabel("Find a workflow").waitFor()
      }
      ok(`${width}: first and last step of ${ids.length} workflows opened`)
    }
    await page.keyboard.press("Escape")
    await context.close()
  }

  if (quiet) {
    // guidance off: no Workflows item, no Show me how, nothing opens by itself
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
    await context.addInitScript(() => { try { localStorage.setItem("loupe.guidance.off", "1") } catch { /* none */ } })
    const page = await context.newPage()
    await page.goto(`${login.url}/cases/${C}/financial?view=overview`, { waitUntil: "domcontentloaded" })
    await page.getByText("Money in this scope").first().waitFor({ timeout: 120_000 })
    await page.waitForTimeout(3000)
    const opened = await page.getByTestId("workflow-guide").count()
    if (opened) bad("guidance off: a workflow opened by itself")
    else ok("guidance off: no workflow opened by itself")
    await page.screenshot({ path: join(out, "guidance-off-1440.png") })
    await context.close()
  }
} catch (e) {
  bad(`stopped: ${e.message.split("\n")[0]}`)
} finally {
  await browser.close()
  writeFileSync(join(out, "report.json"), JSON.stringify(report, null, 2))
  console.log(report.checks.join("\n"))
  console.log(`checks ${report.checks.length}, failed ${report.failed.length}, broken images ${report.brokenImages.length}, stopped requests ${report.stopped.length}`)
  if (report.brokenImages.length) console.log(report.brokenImages.join("\n"))
  process.exit(report.failed.length || report.brokenImages.length ? 1 : 0)
}
