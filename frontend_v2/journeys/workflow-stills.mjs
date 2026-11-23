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
  // view reads sent as POST: Leads already here, the questions Corroborate offers, a conversation's badges
  /\/api\/cases\/[^/]+\/leads:here$/, /\/api\/cases\/[^/]+\/corroborate\/preview$/, /\/api\/cases\/[^/]+\/corroborate\/around-event$/, /\/api\/phone-analysis\/across-badges$/,
  /\/api\/phones\/timeline\/(index|window|buckets)$/,
  /\/api\/investigation-trail/, /\/api\/trail/, /\/api\/auth\/refresh/,
  /\/api\/history\/cases\/[^/]+$/, /\/api\/request-speed\/page-views$/,
  /\/api\/evidence\/route-check$/, /\/api\/activity\/files$/,
  /\/api\/phones\/map\/(summary|trajectory)$/, // the Map's phone totals and routes (case view permission)
  /\/api\/phones\/conversations\/review\/continue$/, // "Continue reading": the person's open reviews (a read)
  /\/api\/phones\/map\/points$/, /\/api\/phones\/streams\/window$/, /\/api\/phones\/link-analysis\/edges$/, /\/api\/phones\/links\/states$/,
  /\/api\/workspace\/[^/]+\/financial-evidence-changes$/, // what changed in cited payments ("Reads only")
  /\/api\/citations\/resolve$/, // a citation's record, for its link
  /\/api\/phones\/media\/(index|window|facets|image-index\/describe|derive-batches\/describe)$/, // Media counts and lists (case view)
  /\/api\/financial\/statement-import\/[^/]+\/(coverage-check|checks)$/, // a statement's date overlaps and checks (reads)
  /\/api\/financial\/judgements\/preview$/, // the calls on a reading before it is saved ("Stores nothing")
]

// Phone lists that also record a search on the case when the filter holds words (the review coverage's searches
// run): let through only with no words in the filter.
const READ_WITHOUT_WORDS = [/\/api\/phones\/conversations\/threads$/, /\/api\/phones\/streams\/index$/]
const noWords = (q) => {
  try {
    return !String(q.postDataJSON()?.text?.query ?? "").trim()
  } catch {
    return false
  }
}

const BUSY = /\d+ of \d+ parts? loaded|Loading the |Loading [^\n]*(…|\.\.\.)|Working out |Still working/

/** What a picture's recipe can do: the moves a person makes. */
function helpers(page, base, width) {
  const h = {
    width,
    phone: width < 640,
    /** A taller screen for one picture whose element does not fit a phone's height; reset after the picture. */
    async tall(height = 1700) {
      await page.setViewportSize({ width, height })
    },
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
      // a panel the last picture opened can come back with the page (a payment's details at phone width): shut it
      if (await page.locator('[role="dialog"]').filter({ visible: true }).count()) {
        await page.keyboard.press("Escape")
        await h.settle(500)
      }
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
  "money-penn": async (h) => searchPayments(h, "PENN"),
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
    return { mark: h.button(/^Jobs/) }
  },
  "ev-copies": async (h) => {
    await h.go("evidence", "PH6")
    await h.dbl(h.css("main").getByText("statements", { exact: true }))
    await h.dbl(h.css("main").getByText("state-exhibits", { exact: true }))
    return { mark: h.css("main table, main [role=grid]") }
  },
  "ev-deleted": async (h) => {
    await h.go("evidence", "PH6")
    return { mark: h.guide("evidence-deleted") }
  },
  "ev-deleted-list": async (h) => {
    await h.go("evidence", "PH6")
    await h.click(h.guide("evidence-deleted"))
    return { mark: h.css('[data-testid="deleted-items"]') }
  },
  "gr-deleted": async (h) => {
    await h.go("graph", "")
    return { mark: h.css('[aria-label="Deleted items"]') }
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
    // at phone width the thread list folds into a Threads button beside the messages
    return { mark: h.phone ? h.text(/^Threads \(\d+\)$/) : h.guide("conversations-list") }
  },
  "ph-conv-search": async (h) => {
    await h.go("conversations", "")
    // typing a search here records it on the case (the review coverage's searches run), so the box is only marked
    return { mark: h.css('input[placeholder="Contains these words"]') }
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
    await h.click(h.text("Travis Kell", true))
    await h.see("SUBJECT DOSSIER")
    return { mark: h.guide("dossiers-detail-tabs") }
  },
  "se-words": async (h) => {
    await h.go("search?q=Kell", "matches")
    return { mark: h.guide("search-heading") }
  },
  "se-meaning": async (h) => {
    await h.go("workspace", "OBJECTIVE")
    await h.click(h.guide("case-search"))
    await h.type(h.css('[role="dialog"] input'), "where were the stolen goods kept")
    await h.see(/By meaning/)
    await h.settle(3000)
    return { mark: h.text(/By meaning/) }
  },
  "ph-media": async (h) => {
    // Phone 5's media (Brianna Cole's phone): the files with their own dates, places and cameras
    await h.go("phones/9fa5612f-3213-4fb2-853d-dcc9baabb4e0/records/media", "Media spread")
    await h.settle(15_000)
    return { mark: h.text("IMG_2041.JPG", true) }
  },
  "ag-source": async (h) => {
    // the thread "What are the $650 monthly payments into the Ruiz Auto & Tire account?", opened by its address
    await h.go("agent?thread=b0a99e52-f218-4b84-9e84-842ad4dd9311", "monthly payments into the Ruiz Auto & Tire account")
    return { mark: h.text(/Source check/) }
  },
  "fin-judgement": async (h) => {
    await h.go("financial?view=statements", "Statements & accounts")
    await h.click(h.text(/^Judgement calls/))
    return { mark: h.text(/^Judgement calls · \d+ on this case/) }
  },
  "fin-compare": async (h) => {
    await h.go("financial?view=statements", "Statements & accounts")
    await h.click(h.text(/^Review queue/))
    await h.click(h.text(/^Copies set aside \d/))
    return { mark: h.button("Compare", true) }
  },
  "fin-compare-open": async (h) => {
    await h.go("financial?view=statements", "Statements & accounts")
    await h.click(h.text(/^Review queue/))
    await h.click(h.text(/^Copies set aside \d/))
    await h.click(h.button("Compare", true))
    await h.see("MATCHING STATEMENT")
    return { mark: h.css('[role="dialog"]').getByText("Opening balance").locator("xpath=ancestor::table[1]") }
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
    return { mark: h.text("OBJECTIVE", true) }
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
    await h.click(h.tab("Tasks & deadlines"))
    return { mark: h.css("main h1, main h2") }
  },
  "ws-theory-compare": async (h) => openTheory(h, () => h.guide("theory-compare")),
  "ws-theory-convert": async (h) => openTheory(h, () => h.guide("theory-convert")),
  "ws-theory-reading": async (h) =>
    openTheory(h, async () => {
      await h.click(h.guide("theory-reading"))
      return h.css('section[aria-label="What breaks this theory"]')
    }),
  "do-new": async (h) => {
    await h.go("dossiers", "Travis Kell")
    return { mark: h.guide("dossiers-new") }
  },
  // Corroborate and leads
  // the classic Corroborate: its pictures are taken with the switch off, as a browser with ?corroborate-v2=off sees it
  "co-payment": async (h) => {
    await searchPayments(h, "POCKETWIRE", "off")
    await h.click(h.text("▸ Details"))
    return { mark: h.button("Corroborate", true) }
  },
  "co-result": async (h) => {
    await h.go("relations/a57b2ccc-5418-418c-b701-abe8ca6e0e5e?corroborate-v2=off", "")
    return { mark: h.guide("relations-candidates") }
  },
  "co-nolink": async (h) => {
    await h.go("relations/a57b2ccc-5418-418c-b701-abe8ca6e0e5e?corroborate-v2=off", "")
    return { mark: h.guide("relations-no-links") }
  },
  "co-header": async (h) => {
    await h.go("relations/a57b2ccc-5418-418c-b701-abe8ca6e0e5e?corroborate-v2=off", "candidate links")
    return { mark: h.guide("relations-header") }
  },
  "co-actions": async (h) => {
    await h.go("relations/a57b2ccc-5418-418c-b701-abe8ca6e0e5e?corroborate-v2=off", "candidate links")
    return { mark: h.guide("relations-actions") }
  },
  // the new Corroborate, switch on
  "co2-payment": async (h) => {
    await searchPayments(h, "POCKETWIRE", "on")
    await h.click(h.text("▸ Details"))
    return { mark: h.button("Corroborate", true) }
  },
  "co2-question": async (h) => {
    await searchPayments(h, "POCKETWIRE", "on")
    await h.click(h.text("▸ Details"))
    await h.click(h.button("Corroborate", true))
    await h.click(h.guide("corroborate-panel-ask"))
    await h.see("What do you want to know?")
    await h.settle(2000)
    return { mark: h.guide("corroborate-panel-ask"), crop: h.guide("corroborate-panel") }
  },
  "co2-panel": async (h) => {
    await searchPayments(h, "POCKETWIRE", "on")
    await h.click(h.text("▸ Details"))
    await h.click(h.button("Corroborate", true))
    await h.see(/Leads already here \d/)
    await h.settle(2000)
    return { mark: h.guide("corroborate-panel-here"), crop: h.guide("corroborate-panel") }
  },
  "money-around": async (h) => {
    await h.go("financial/around-event?corroborate-v2=on", "Dates the case states")
    await h.click(h.text(/^Dates the case states/))
    // the five theft nights, each dated by its police report: a pattern needs two or more events
    for (const d of ["2024-03-16", "2024-04-13", "2024-05-04", "2024-05-18", "2024-06-01"]) {
      await h.click(h.css(`label:has-text("${d}: police-report") input[type="checkbox"]`))
      await h.settle(500)
    }
    await h.settle(4000)
    return { mark: h.css('[data-testid="money-cell"]') }
  },
  "do-overlaps": async (h) => {
    await h.go("dossiers?corroborate-v2=on", "Travis Kell")
    await h.click(h.guide("dossiers-overlaps"))
    await h.settle(4000)
    return { mark: h.css('main h2:has-text("Who overlaps with whom")') }
  },
  "gr-overlap": async (h) => {
    await h.go("graph?corroborate-v2=on&graph-mode=people", "")
    await h.settle(5000)
    return { mark: h.css('svg[aria-label="People, go-betweens and documents"]') }
  },
  "ph-elsewhere": async (h) => elsewhere(h, "Dee, Travis Kell"),
  "leads-show": async (h) => {
    await h.go("leads?corroborate-v2=on", "")
    await h.settle()
    return { mark: h.guide("lead-show-records") }
  },
  "leads-filters": async (h) => {
    await h.go("leads?corroborate-v2=on", "Look for leads now")
    return { mark: h.guide("leads-filters") }
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
    await h.go("agent?thread=b0a99e52-f218-4b84-9e84-842ad4dd9311", "monthly payments into the Ruiz Auto & Tire account")
    return { mark: h.css("main article, main [data-message-role='assistant']") }
  },
  "ag-ask": async (h) => {
    await h.go("agent", "What can I ask?")
    return { mark: h.css('textarea[aria-label="Agent request"]') }
  },
  "ag-deep": async (h) => {
    await h.go("agent", "What can I ask?")
    return { mark: h.guide("agent-deep") }
  },
  "ag-workflows": async (h) => {
    await h.go("agent", "What can I ask?")
    return { mark: h.text("Or start a guided workflow") }
  },
  // The assistant's guided workflows: the row opened with Use, its steps and what the demo case holds for each
  "ag-wf-last-proof-of-life": async (h) => assistantWorkflow(h, "Last proof of life"),
  "ag-wf-hidden-assets": async (h) => assistantWorkflow(h, "Hidden assets"),
  "ag-wf-carer-abuse": async (h) => assistantWorkflow(h, "Power-of-attorney and carer abuse"),
  "ag-wf-procurement-kickbacks": async (h) => assistantWorkflow(h, "Procurement kickbacks"),
  "ag-wf-expense-fraud": async (h) => assistantWorkflow(h, "Expense and travel fraud"),
  "ag-wf-insider-trading": async (h) => assistantWorkflow(h, "Insider trading"),
  "ag-wf-payment-scam-victim": async (h) => assistantWorkflow(h, "Payment-scam victims"),
  "ag-wf-drug-proceeds": async (h) => assistantWorkflow(h, "Drug-supply turnover and proceeds"),
  "ag-wf-staged-accident": async (h) => assistantWorkflow(h, "Staged-accident insurance fraud"),
  "ag-wf-defence-review": async (h) => assistantWorkflow(h, "Defence and review"),
  "ag-wf-county-lines": async (h) => assistantWorkflow(h, "County lines"),
  "ag-wf-coercive-control": async (h) => assistantWorkflow(h, "Coercive control"),
  "ag-wf-human-trafficking": async (h) => assistantWorkflow(h, "Human trafficking"),
  "ag-wf-sanctions-evasion": async (h) => assistantWorkflow(h, "Sanctions evasion"),
  "ag-wf-money-laundering": async (h) => assistantWorkflow(h, "Money laundering"),
  "ag-wf-embezzlement": async (h) => assistantWorkflow(h, "Embezzlement"),
  "ag-wf-organised-retail-crime": async (h) => assistantWorkflow(h, "Organised retail crime"),
  "ag-wf-disconfirm-theory": async (h) => assistantWorkflow(h, "What breaks this theory"),
  "ag-wf-link-group": async (h) => assistantWorkflow(h, "Corroborate"),
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

/** Conversations with one thread open and Mark what also appears elsewhere ticked: its list of shared words marked. */
async function elsewhere(h, thread) {
  await h.go("conversations?corroborate-v2=on", "")
  if (h.phone) await h.click(h.text(/^Threads \(\d+\)$/))
  await h.click(h.css(`[data-guide="conversations-list"] :text-is("${thread}")`))
  await h.settle()
  await h.click(h.css('[data-testid="also-elsewhere-toggle"] input'))
  await h.settle(4000)
  // the Also elsewhere list: the words on two or more phones, and what was deleted on one phone and kept on another
  const list = h.text("Words also on other phones", true)
  return { mark: (await list.count()) ? list : h.guide("also-elsewhere") }
}

/** Theory T2 open in Casework; `mark` names the part of the theory to ring. */
async function openTheory(h, mark) {
  await h.go("workspace?view=casework&kind=theory", "T2 ")
  await h.click(h.css("main").getByText(/^T2 /).first())
  await h.see(h.guide("theory-panel"))
  return { mark: await mark() }
}

/** Agent, a new thread, the guided workflow's row opened with Use: its steps and whether each can run on this case. */
async function assistantWorkflow(h, title) {
  // Agent opens on a new thread, whose empty state offers the guided workflows; on a phone the row with its steps is
  // taller than the space under the thread's header, so the picture is taken on a taller screen to keep the whole row
  if (h.phone) await h.tall()
  await h.go("agent", "What can I ask?")
  const picker = h.text("Or start a guided workflow")
  if (!(await picker.isVisible())) await h.click(h.button("New agent thread"))
  await h.see("Or start a guided workflow")
  const use = h.button(`Use workflow ${title}`, true)
  // workflows past the first ten wait behind "Show 9 more workflows"
  const more = h.button(/^Show \d+ more workflows/)
  if (!(await use.isVisible()) && (await more.isVisible())) await h.click(more)
  await use.waitFor({ state: "visible", timeout: 120_000 })
  await use.scrollIntoViewIfNeeded()
  // a workflow the case cannot run has its Use switched off: the row, with its reason, is the picture
  if (await use.isEnabled()) {
    await use.evaluate((e) => e.click())
    await h.settle()
  }
  const row = use.locator("xpath=ancestor::li[1]")
  const start = row.getByRole("button", { name: "Start workflow" })
  // at phone width the row's top sits under the thread's sticky header: the row's own Start workflow is the mark there
  const mark = h.phone && (await start.count()) ? start.first() : row
  // scroll the row to just below the thread header (Using case objective), which stays on screen above the list;
  // at phone width the row's title shows too when its Start workflow still fits on the screen
  await row.evaluate((r, m) => {
    const header = [...document.querySelectorAll("main *")].find((x) => x.textContent?.trim() === "Override for next request")
    const below = header ? header.getBoundingClientRect().bottom + 24 : 120
    let box = r.parentElement
    while (box && !(box.scrollHeight > box.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) box = box.parentElement
    const target = m ?? r
    const bottom = box ? box.getBoundingClientRect().bottom : window.innerHeight
    const fits = target.getBoundingClientRect().bottom - r.getBoundingClientRect().top <= bottom - below - 16
    const by = (fits ? r : target).getBoundingClientRect().top - below
    if (box) box.scrollTop += by
    else window.scrollBy(0, by)
  }, mark === row ? null : await mark.elementHandle())
  await h.settle(500)
  return h.phone ? { mark, crop: row, whole: true } : { mark }
}

/** The Transactions list with the search box filled, the count of matching payments marked. */
async function searchPayments(h, words, corroborate) {
  // corroborate: "on" or "off" sets the Corroborate switch for this picture through the address
  await h.go(`financial?view=transactions${corroborate ? `&corroborate-v2=${corroborate}` : ""}`, "imported transactions in this case")
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
    // every picture starts with the switches off, as a person's browser does; a recipe that shows switched-off work
    // turns its switch on through the address (?corroborate-v2=on, ?phone_layers=on), which the app reads after this
    await context.addInitScript(() => {
      try {
        localStorage.removeItem("loupe.switch.corroborate-v2")
        localStorage.removeItem("loupe.phone_layers")
        // each picture starts with no Corroborate selection: an earlier picture's Corroborate would fill the tray
        for (const k of Object.keys(localStorage)) if (k.startsWith("loupeCorroSelection:")) localStorage.removeItem(k)
      } catch { /* storage unavailable: switches stay off */ }
    })
    const page = await context.newPage()
    await page.route("**/api/**", (r) => {
      const q = r.request()
      const path = new URL(q.url()).pathname
      if (["GET", "HEAD", "OPTIONS"].includes(q.method()) || READ_ONLY_POSTS.some((p) => p.test(path))) return r.continue()
      if (READ_WITHOUT_WORDS.some((p) => p.test(path)) && noWords(q)) return r.continue()
      report.stopped.push(`${q.method()} ${path}`)
      return r.abort()
    })
    // Every job signs in with the one jobs login, so another job's agent run on the demo case reads as this person's
    // and the Agent page opens on it. The pictures show the page as a person with no run going sees it.
    await page.route("**/api/agent/runs/active**", (r) => r.fulfill({ json: { runs: [] } }))
    for (const [name, recipe] of Object.entries(SHOTS)) {
      if (only && !only.has(name)) continue
      const h = helpers(page, login.url, width)
      try {
        const { mark, crop, whole } = await recipe(h)
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
        // whole: keep the crop element from its top down to the control, on the taller screen the recipe asked for
        const clip = whole && area
          ? { x: Math.max(0, Math.round(area.x - 8)), y: Math.max(0, Math.round(area.y - 8)), width: Math.round(Math.min(area.width + 16, vp.width - Math.max(0, area.x - 8))),
              height: Math.round(Math.min(box.y + box.height + 20, vp.height) - Math.max(0, area.y - 8)) }
          : cropBox(box, area, vp, h.phone)
        const png = join(scratch, `${name}-${width}.png`)
        await page.screenshot({ path: png, clip, timeout: 120_000 })
        await page.evaluate(() => document.getElementById("workflow-still-mark")?.remove())
        const webp = join(OUT, `${name}-${width}.webp`)
        execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", png, "-c:v", "libwebp", "-quality", "72", webp])
        if (dump) {
          const info = await page.evaluate(() => ({
            url: location.pathname + location.search,
            guides: [...new Set([...document.querySelectorAll("[data-guide]")].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.getAttribute("data-guide")))],
            text: [document.querySelector("main") || document.body, ...document.querySelectorAll('[role="dialog"]')].map((e) => e.innerText).join("\n[dialog]\n").slice(0, 12000),
          }))
          writeFileSync(join(dump, `${name}-${width}.json`), JSON.stringify(info, null, 1))
        }
        if (whole) await page.setViewportSize({ width, height: width < 640 ? 844 : 900 })
        report.taken.push(`${name}-${width}`)
        console.log("took", name, width)
      } catch (e) {
        report.failed.push({ shot: `${name}-${width}`, error: String(e.message || e).slice(0, 300) })
        console.log("FAILED", name, width, String(e.message || e).slice(0, 200))
        // with --dump, what the screen showed when the recipe gave up
        if (dump) await page.screenshot({ path: join(dump, `${name}-${width}-failed.png`) }).catch(() => {})
        await page.setViewportSize({ width, height: width < 640 ? 844 : 900 })
      }
    }
    await context.close()
  }
} finally {
  await browser.close()
  rmSync(scratch, { recursive: true, force: true })
}
console.log(JSON.stringify({ taken: report.taken.length, failed: report.failed, stopped: [...new Set(report.stopped)] }, null, 1))
// "is also reviewing this thread" is a write the pictures never need; it is stopped and listed, and fails nothing
const EXPECTED_STOPS = [/^POST \/api\/phones\/conversations\/presence$/]
process.exit(report.failed.length || report.stopped.some((r) => !EXPECTED_STOPS.some((p) => p.test(r))) ? 1 : 0)

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
