#!/usr/bin/env node
// The pictures of the Workflows section of the Guide (lx-workflowguide E), taken from the live demo case.
// Signed in once with the jobs login over plain http; read only: a request that is not a GET is stopped unless it is
// on READ_ONLY_POSTS (view-only reads sent as POST), and every stopped request is reported.
//
//   node journeys/workflow-stills.mjs [--only money-overview,money-search] [--width 1440|390] [--dump <dir>]
//
// Each picture is one entry of SHOTS below: it opens a screen of the demo case, does what a person would do to reach
// the step, marks the control the step names with a ring, crops to the part of the screen that matters and writes
// public/docs/workflows/img/<shot>-<width>.webp at 1440 and 390 wide. --dump also writes the screen's words and its
// guide anchors to <dir>/<shot>-<width>.json, to check a step's expected result against what the screen shows.
// After a change to a screen, run it again with no arguments: every picture is taken afresh.
import { execFileSync } from "node:child_process"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const here = dirname(fileURLToPath(import.meta.url))
const OUT = join(here, "..", "public", "docs", "workflows", "img")
const only = arg("only") ? new Set(arg("only").split(",")) : null
const widths = arg("width") ? [Number(arg("width"))] : [1440, 390]
const dump = arg("dump")
const C = CASES.demo
const READ_ONLY_POSTS = [
  /\/api\/phones\/timeline\/(index|window|buckets)$/,
  /\/api\/investigation-trail/, /\/api\/trail/, /\/api\/auth\/refresh/,
  /\/api\/history\/cases\/[^/]+$/, /\/api\/request-speed\/page-views$/,
  /\/api\/evidence\/route-check$/, /\/api\/activity\/files$/,
  /\/api\/phones\/map\/(summary|trajectory)$/, // the Map's phone totals and routes (case view permission)
  /\/api\/phones\/conversations\/review\/continue$/, // "Continue reading": the person's open reviews (a read)
]

const BUSY = /\d+ of \d+ parts? loaded|Loading the |Loading [^\n]*(…|\.\.\.)|Working out |Still working/

/** What a picture's recipe can do: the moves a person makes. */
function helpers(page, base, width) {
  const h = {
    width,
    phone: width < 640,
    async settle(ms = 1500) {
      await page.waitForTimeout(800)
      await page.waitForFunction((re) => !new RegExp(re).test(document.body.innerText), BUSY.source, { timeout: 120_000, polling: 500 }).catch(() => {})
      await page.waitForTimeout(ms)
    },
    async go(route, waitFor) {
      await page.goto(`${base}/cases/${C}/${route}`, { waitUntil: "domcontentloaded" })
      if (waitFor) await h.see(waitFor)
      else await h.see(page.locator("main"))
      await h.settle()
    },
    async see(text, opts = {}) {
      const l = typeof text === "string" || text instanceof RegExp ? page.getByText(text, { exact: false, ...opts }).filter({ visible: true }).first() : text
      await l.waitFor({ state: "visible", timeout: 120_000 })
      return l
    },
    button: (name, exact = false) => page.getByRole("button", { name, exact }).first(),
    tab: (name) => page.getByRole("tab", { name }).first(),
    link: (name) => page.getByRole("link", { name }).first(),
    text: (t, exact = false) => page.getByText(t, { exact }).filter({ visible: true }).first(),
    guide: (name) => page.locator(`[data-guide="${name}"]`).filter({ visible: true }).first(),
    css: (sel) => page.locator(sel).filter({ visible: true }).first(),
    async click(l) {
      await l.waitFor({ state: "visible", timeout: 120_000 })
      await l.click()
      await h.settle()
    },
    async dbl(l) {
      await l.first().waitFor({ state: "visible", timeout: 120_000 })
      await l.first().dblclick()
      await h.settle()
    },
    async type(l, value) {
      await l.waitFor({ state: "visible", timeout: 120_000 })
      await l.fill(value)
      await h.settle()
    },
    // the side menu is shut at phone width: open it before a step points into it
    async menu() {
      if (!h.phone) return
      const open = page.getByRole("button", { name: /open (the )?(side )?menu|open navigation/i }).first()
      if (await open.isVisible().catch(() => false)) await h.click(open)
    },
  }
  return h
}

/**
 * Every picture. A recipe returns the control to mark (`mark`) and, if the part of the screen that matters is not
 * the area round that control, the element to crop to (`crop`). Names follow catalogue.ts `shot` fields.
 */
export const SHOTS = {
  // Where did the money go? (Financial)
  "money-overview": async (h) => {
    await h.go("financial?view=overview", "Money in this scope")
    return { mark: h.text("Money in this scope").locator("xpath=ancestor::*[.//*[contains(., 'Net movement')]][1]") }
  },
  "money-cash": async (h) => searchPayments(h, "CASH"),
  "money-pocketwire": async (h) => searchPayments(h, "POCKETWIRE"),
  "money-rent": async (h) => searchPayments(h, "BAY 4 RENT"),
  "money-details": async (h) => {
    await searchPayments(h, "CASH")
    await h.click(h.text("▸ Details"))
    return { mark: h.button("Open original statement"), crop: h.text("▾ Details").locator("xpath=ancestor::*[.//button[contains(., 'Open original statement')]][1]") }
  },
  "money-statement": async (h) => {
    await searchPayments(h, "CASH")
    await h.click(h.text("▸ Details"))
    await h.click(h.button("Open original statement"))
    return { mark: h.text(/Checked against the statement/) }
  },
  "money-held": async (h) => {
    await h.go("financial?view=overview", "Money in this scope")
    return { mark: h.button(/Check the 1 statement/) }
  },
  "money-findings": async (h) => {
    await h.go("financial?view=findings", "Findings & Observations")
    return { mark: h.button("Create finding") }
  },
  // Evidence
  "ev-root": async (h) => {
    await h.go("evidence", "PH6")
    return { mark: h.guide("evidence-upload") }
  },
  "ev-phone-add": async (h) => {
    await h.go("evidence", "PH6")
    return { mark: h.button("Add phone report (folder or ZIP)") }
  },
  "ev-documents": async (h) => {
    await h.go("evidence", "PH6")
    await h.dbl(h.css("main").getByText("documents", { exact: true }))
    return { mark: h.button("Process", true) }
  },
  "ev-jobs": async (h) => {
    await h.go("evidence", "PH6")
    await h.click(h.button(/^Jobs/))
    return { mark: h.guide("jobs-panel") }
  },
  "ev-copies": async (h) => {
    await h.go("evidence", "PH6")
    await h.dbl(h.css("main").getByText("statements", { exact: true }))
    await h.dbl(h.css("main").getByText("state-exhibits", { exact: true }))
    return { mark: h.css("main table, main [role=grid]") }
  },
  "ev-deleted": async (h) => {
    await h.go("evidence", "PH6")
    await h.click(h.guide("evidence-deleted"))
    return { mark: h.guide("evidence-deleted") }
  },
  "ev-photo": async (h) => {
    await h.go("evidence", "PH6")
    await h.dbl(h.css("main").getByText("documents", { exact: true }))
    return { mark: h.css("main").getByText(/\.(jpg|jpeg|png)$/i) }
  },
  // Phones
  "ph-index": async (h) => {
    await h.go("phones", "Phone 6")
    return { mark: h.text("Phone 3") }
  },
  "ph-summary": async (h) => {
    await h.go("phones", "Phone 6")
    await h.click(h.text("Phone 3"))
    return { mark: h.css("main h1, main h2") }
  },
  "ph-compare": async (h) => {
    await h.go("phones", "Phone 6")
    await h.click(h.button("Compare phones"))
    return { mark: h.css("main h1, main h2") }
  },
  "ph-conversations": async (h) => {
    await h.go("conversations", "")
    return { mark: h.guide("conversations-list") }
  },
  "ph-conv-search": async (h) => {
    await h.go("conversations", "")
    await h.type(h.css('[data-guide="conversations-filters"] input, main input[type="search"], main input[placeholder*="Search" i]'), "tow truck")
    return { mark: h.guide("conversations-list") }
  },
  "an-index": async (h) => {
    await h.go("phone-analyses", "")
    return { mark: h.guide("analyses-list") }
  },
  "an-common": async (h) => {
    await h.go("phone-analyses/common-contacts", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-matrix": async (h) => {
    await h.go("phone-analyses/who-contacts-whom", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-deletions": async (h) => {
    await h.go("phone-analyses/deletions", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-readagain": async (h) => {
    await h.go("phone-analyses/read-again", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-incident": async (h) => {
    await h.go("phone-analyses/incident-window", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-relationships": async (h) => {
    await h.go("phone-analyses/relationships", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-monitoring": async (h) => {
    await h.go("phone-analyses/monitoring-apps", "")
    return { mark: h.css("main h1, main h2") }
  },
  "an-numbers": async (h) => {
    await h.go("phone-analyses/number-changes", "")
    return { mark: h.css("main h1, main h2") }
  },
  "ph-money": async (h) => {
    await h.go("phone-money", "")
    return { mark: h.css("main h1, main h2") }
  },
  "ph-patterns": async (h) => {
    await h.go("phone-patterns", "")
    return { mark: h.guide("pattern-views") }
  },
  // Map and timeline
  "map-canvas": async (h) => {
    await h.go("map", "")
    await h.settle(8000)
    return { mark: h.guide("map-canvas") }
  },
  "map-routes": async (h) => {
    await h.go("map", "")
    await h.settle(8000)
    return { mark: h.guide("map-routes") }
  },
  "map-areas": async (h) => {
    await h.go("map", "")
    await h.settle(5000)
    return { mark: h.guide("map-areas") }
  },
  "map-layers": async (h) => {
    await h.go("map?phone_layers=on", "")
    await h.settle(8000)
    return { mark: h.guide("phone-layers") }
  },
  "tl-range": async (h) => {
    await h.go("timeline", "Custom")
    await h.click(h.button("Custom", true))
    const d = h.css('input[type="date"]').page().locator('input[type="date"]')
    await d.nth(0).fill("2024-03-01")
    await d.nth(1).fill("2024-06-10")
    await h.settle(3000)
    return { mark: h.guide("timeline-toolbar") }
  },
  "tl-phones": async (h) => {
    await h.go("timeline", "Custom")
    await h.click(h.button(/^Phones \(/))
    return { mark: h.button(/^Phones \(/) }
  },
  "tl-add": async (h) => {
    await h.go("timeline", "Custom")
    return { mark: h.button("Add this range to theory…") }
  },
  // Graph, table, dossiers, search
  "gr-canvas": async (h) => {
    await h.go("graph", "items")
    await h.settle(5000)
    return { mark: h.css("canvas") }
  },
  "gr-people": async (h) => {
    await h.go("graph", "items")
    await h.click(h.guide("graph-people-in-contact"))
    return { mark: h.guide("graph-people-in-contact") }
  },
  "gr-search": async (h) => {
    await h.go("graph", "items")
    await h.type(h.css('main input[placeholder*="Search" i]'), "Travis Kell")
    return { mark: h.css('main input[placeholder*="Search" i]') }
  },
  "table-grid": async (h) => {
    await h.go("table", "")
    return { mark: h.guide("table-toolbar") }
  },
  "do-list": async (h) => {
    await h.go("dossiers", "Travis Kell")
    return { mark: h.guide("dossiers-list") }
  },
  "do-kell": async (h) => {
    await h.go("dossiers", "Travis Kell")
    await h.click(h.text("Travis Kell"))
    return { mark: h.guide("dossiers-detail-tabs") }
  },
  "se-words": async (h) => {
    await h.go("search?q=Kell", "matches")
    return { mark: h.guide("search-heading") }
  },
  "se-meaning": async (h) => {
    await h.go("search?q=where%20were%20the%20stolen%20goods%20stored&mode=meaning", "")
    return { mark: h.guide("search-hits") }
  },
  "se-box": async (h) => {
    await h.go("workspace", "")
    await h.click(h.guide("case-search"))
    return { mark: h.css('[role="dialog"] input, [cmdk-input]') }
  },
  "kw-lists": async (h) => {
    await h.go("keyword-lists", "")
    return { mark: h.guide("keywords-intro") }
  },
  // Workspace and theories
  "ws-home": async (h) => {
    await h.go("workspace", "OBJECTIVE")
    return { mark: h.guide("case-objective") }
  },
  "ws-theories": async (h) => {
    await h.go("workspace?view=casework&kind=theory", "")
    return { mark: h.css("main").getByText(/^T2 /).first() }
  },
  "ws-theory": async (h) => {
    await h.go("workspace?view=casework&kind=theory", "")
    await h.click(h.css("main").getByText(/^T2 /).first())
    return { mark: h.guide("theory-links") }
  },
  "ws-theory-review": async (h) => {
    await h.go("workspace?view=casework&kind=theory", "")
    await h.click(h.css("main").getByText(/^T2 /).first())
    return { mark: h.guide("theory-review") }
  },
  "ws-tasks": async (h) => {
    await h.go("workspace", "OBJECTIVE")
    await h.click(h.button("Tasks & deadlines", true))
    return { mark: h.css("main h1, main h2") }
  },
  // Corroborate and leads
  "co-payment": async (h) => {
    await searchPayments(h, "POCKETWIRE")
    await h.click(h.text("▸ Details"))
    return { mark: h.button("Corroborate", true) }
  },
  "co-result": async (h) => {
    await h.go("relations/a57b2ccc-5418-418c-b701-abe8ca6e0e5e", "")
    return { mark: h.guide("relations-candidates") }
  },
  "co-nolink": async (h) => {
    await h.go("relations/a57b2ccc-5418-418c-b701-abe8ca6e0e5e", "")
    return { mark: h.guide("relations-no-links") }
  },
  "co-tray": async (h) => {
    await h.go("financial?view=transactions&corroborate-v2=on", "imported transactions in this case")
    return { mark: h.guide("corroborate-tray") }
  },
  "co-claim": async (h) => {
    await h.go("workspace?corroborate-v2=on", "OBJECTIVE")
    return { mark: h.guide("corroborate-claim") }
  },
  "leads-list": async (h) => {
    await h.go("leads?corroborate-v2=on", "")
    return { mark: h.guide("leads-find") }
  },
  // The assistant
  "ag-thread": async (h) => {
    await h.go("agent", "Agent threads")
    await h.click(h.text("What are the $650 monthly payments"))
    return { mark: h.css("main article, main [data-message-role='assistant']") }
  },
  "ag-ask": async (h) => {
    await h.go("agent", "Agent threads")
    return { mark: h.css('textarea[aria-label="Agent request"]') }
  },
  "ag-deep": async (h) => {
    await h.go("agent", "Agent threads")
    return { mark: h.guide("agent-deep") }
  },
  "ag-tools": async (h) => {
    await h.go("agent", "Agent threads")
    return { mark: h.guide("agent-tools") }
  },
  "ag-workflows": async (h) => {
    await h.go("agent", "Agent threads")
    await h.click(h.button("New agent thread"))
    return { mark: h.text("Or start a guided workflow") }
  },
  // Reports and financial checks
  "rp-casework": async (h) => {
    await h.go("reports", "Casework report")
    return { mark: h.guide("reports-casework") }
  },
  "rp-financial": async (h) => {
    await h.go("reports", "Casework report")
    return { mark: h.guide("reports-financial") }
  },
  "fin-statements": async (h) => {
    await h.go("financial?view=statements", "")
    return { mark: h.css("main h1, main h2") }
  },
  "fin-calls": async (h) => {
    await h.go("financial?view=overview", "Money in this scope")
    return { mark: h.text("49 calls Loupe made for you") }
  },
  "fin-coverage": async (h) => {
    await h.go("financial?view=overview", "Money in this scope")
    return { mark: h.button("Check dates and missing statements") }
  },
  "fin-name": async (h) => {
    await searchPayments(h, "POCKETWIRE")
    return { mark: h.button("Name them one by one") }
  },
}

/** The Transactions list with the search box filled, the count of matching payments marked. */
async function searchPayments(h, words) {
  await h.go("financial?view=transactions", "imported transactions in this case")
  await h.type(h.css('input[placeholder*="Search payments" i], input[aria-label*="Search payments" i]'), words)
  await h.see(/\d+ of 210 imported transactions/)
  return { mark: h.text(/\d+ of 210 imported transactions/) }
}

const login = readLogin()
const browser = await chromium.launch()
const report = { taken: [], failed: [], stopped: [] }
mkdirSync(OUT, { recursive: true })
if (dump) mkdirSync(dump, { recursive: true })
const scratch = join("/mnt/owl-data/tmp", `workflow-stills-${process.pid}`)
mkdirSync(scratch, { recursive: true })
try {
  const { context: first } = await signIn(browser, login)
  const state = await first.storageState()
  await first.close()
  for (const width of widths) {
    const context = await browser.newContext({
      viewport: { width, height: width < 640 ? 844 : 900 },
      deviceScaleFactor: width < 640 ? 2 : 1,
      storageState: state,
    })
    // guidance popups (tours, Start here) stay out of the pictures
    await context.addInitScript(() => {
      try { sessionStorage.setItem("loupe.stills", "1") } catch { /* storage unavailable */ }
    })
    const page = await context.newPage()
    await page.route("**/api/**", (r) => {
      const q = r.request()
      const path = new URL(q.url()).pathname
      if (["GET", "HEAD", "OPTIONS"].includes(q.method()) || READ_ONLY_POSTS.some((p) => p.test(path))) return r.continue()
      report.stopped.push(`${q.method()} ${path}`)
      return r.abort()
    })
    for (const [name, recipe] of Object.entries(SHOTS)) {
      if (only && !only.has(name)) continue
      const h = helpers(page, login.url, width)
      try {
        const { mark, crop } = await recipe(h)
        await mark.waitFor({ state: "visible", timeout: 120_000 })
        await mark.scrollIntoViewIfNeeded().catch(() => {})
        await page.waitForTimeout(400)
        const box = await mark.boundingBox()
        // close any tour popup that opened by itself, and draw the ring round the control
        await page.evaluate((b) => {
          document.querySelectorAll('[data-testid="tour-popup"]').forEach((e) => e.remove())
          const ring = document.createElement("div")
          ring.id = "workflow-still-mark"
          Object.assign(ring.style, {
            position: "fixed", zIndex: "2147483647", pointerEvents: "none", borderRadius: "8px",
            left: `${b.x - 6}px`, top: `${b.y - 6}px`, width: `${b.width + 12}px`, height: `${b.height + 12}px`,
            border: "3px solid hsl(var(--primary))", boxShadow: "0 0 0 4px hsl(var(--primary) / 0.25)",
          })
          document.body.appendChild(ring)
        }, box)
        const vp = page.viewportSize()
        const area = crop ? await crop.boundingBox() : null
        const clip = cropBox(box, area, vp, h.phone)
        const png = join(scratch, `${name}-${width}.png`)
        await page.screenshot({ path: png, clip, timeout: 120_000 })
        await page.evaluate(() => document.getElementById("workflow-still-mark")?.remove())
        const webp = join(OUT, `${name}-${width}.webp`)
        execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", png, "-c:v", "libwebp", "-quality", "72", webp])
        if (dump) {
          const info = await page.evaluate(() => ({
            url: location.pathname + location.search,
            guides: [...new Set([...document.querySelectorAll("[data-guide]")].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.getAttribute("data-guide")))],
            text: (document.querySelector("main") || document.body).innerText.slice(0, 8000),
          }))
          writeFileSync(join(dump, `${name}-${width}.json`), JSON.stringify(info, null, 1))
        }
        report.taken.push(`${name}-${width}`)
        console.log("took", name, width)
      } catch (e) {
        report.failed.push({ shot: `${name}-${width}`, error: String(e.message || e).slice(0, 300) })
        console.log("FAILED", name, width, String(e.message || e).slice(0, 200))
      }
    }
    await context.close()
  }
} finally {
  await browser.close()
  rmSync(scratch, { recursive: true, force: true })
}
console.log(JSON.stringify({ taken: report.taken.length, failed: report.failed, stopped: [...new Set(report.stopped)] }, null, 1))
process.exit(report.failed.length || report.stopped.length ? 1 : 0)

/** The part of the screen a picture keeps: the crop element, or a window round the control, inside the viewport. */
function cropBox(mark, area, vp, phone) {
  const W = vp.width
  const H = phone ? 620 : 640
  if (area) {
    const top = Math.max(0, Math.min(area.y, mark.y - 80))
    const x = Math.max(0, area.x)
    const width = Math.min(W - x, area.width)
    const height = Math.min(vp.height - top, Math.max(H, Math.min(area.height, H)))
    return fitAround(mark, { x, y: top, width, height }, vp, H)
  }
  return fitAround(mark, { x: 0, y: 0, width: W, height: H }, vp, H)
}

function fitAround(mark, box, vp, H) {
  // keep the control inside, a third of the way down when the window is taller than it
  const height = Math.min(H, vp.height)
  let y = Math.round(mark.y + mark.height / 2 - height / 3)
  y = Math.max(0, Math.min(y, vp.height - height))
  return { x: Math.round(box.x), y, width: Math.round(Math.min(box.width, vp.width - box.x)), height }
}
