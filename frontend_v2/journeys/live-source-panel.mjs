#!/usr/bin/env node
// Live check of the record view's source database panel (05 17.2, stage J item D): signed in once with the jobs login
// over plain http, in the restricted phone reference cases only (CB-INDEX P3). For each record: open the record, time
// until the panel shows, press "Open source row" / "Open source database", time until a progress panel or the data
// shows (page standard: progress or data within 2 s, data within 10 s), and screenshot the panel with the row's values,
// file paths and table names masked. Prints counts, states and milliseconds only, never case text.
//   node journeys/live-source-panel.mjs --shots <dir> --case phoneRef1|phoneRef2|phoneRef3 --records uid[,uid...]
//     [--labels P12[,P07...]]
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { PHONE_REFERENCE_CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const shots = arg("shots")
const caseId = PHONE_REFERENCE_CASES[arg("case")]
const records = (arg("records", "") || "").split(",").filter(Boolean)
const labels = (arg("labels", "") || "").split(",")
if (!shots || !caseId || !records.length) {
  console.error("usage: --shots <dir> --case phoneRef1|phoneRef2|phoneRef3 --records uid[,uid...] [--labels a,b]")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const login = readLogin()
const browser = await chromium.launch()
let failures = 0
try {
  const { context } = await signIn(browser, login)
  const page = await context.newPage()
  const errors = []
  page.on("pageerror", (e) => errors.push(e.message.slice(0, 120)))
  // each API call's own time (request sent to response end), so the server's share is told apart from the page's
  let calls = []
  page.on("requestfinished", (r) => {
    const u = r.url()
    const kind = /\/source-database/.test(u) ? "source-database" : /\/api\/phones\/records\/[^/?]+\?/.test(u) ? "record" : null
    if (!kind) return
    const t = r.timing()
    calls.push(`${kind} ${Math.round(t.responseEnd - t.requestStart)} ms`)
  })
  for (const [i, uid] of records.entries()) {
    const label = labels[i] || `r${i + 1}`
    calls = []
    const t0 = Date.now()
    await page.goto(`${login.url}/cases/${caseId}/records/${uid}`, { waitUntil: "domcontentloaded" })
    if (i === 0 && (await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
    const panel = page.getByRole("region", { name: "Source database" }).or(page.locator('section[aria-label="Source database"]')).first()
    const shown = await panel.waitFor({ timeout: 30000 }).then(() => Date.now() - t0).catch(() => null)
    if (shown === null) {
      failures += 1
      console.log(`${label}: panel not shown within 30 s`)
      continue
    }
    const button = panel.getByRole("button", { name: /^Open source (row|database)$/ })
    const masks = () => [panel.locator("td"), panel.locator("code"), panel.locator("li"), panel.locator("p").filter({ hasText: /\// }),
      panel.locator("p").filter({ hasText: /The bytes at that position/ })]
    const shoot = async (what) => {
      const file = `${shots}/${label}-${what}.png`
      const ok = await panel.screenshot({ path: file, mask: masks(), maskColor: "#888", timeout: 30000 }).then(() => true).catch(() => false)
      return ok ? file.split("/").pop() : "not taken (the panel could not be captured)"
    }
    // the section can render before the case is known, without its button; wait for the button or the final words
    await button.or(panel.getByText(/The production does not include|not in the production|does not match|no bytes|not checked/))
      .first().waitFor({ timeout: 15000 }).catch(() => null)
    if (process.env.LIVE_DEBUG) {
      const all = page.locator('section[aria-label="Source database"]')
      const n = await all.count()
      const states = []
      for (let k = 0; k < n; k++) {
        const t = (await all.nth(k).textContent()) ?? ""
        states.push([/Open source (row|database)/.test(t) ? "button" : "", /does not include/.test(t) ? "none" : "",
          /does not say which row/.test(t) ? "unnamed" : "", `len ${t.length}`].filter(Boolean).join("+"))
      }
      console.log(`${label} debug: ${n} sections [${states.join(" | ")}] at ${Date.now() - t0} ms`)
    }
    if (!(await button.count())) {
      const kind = (await panel.textContent()).includes("The production does not include") ? "no linked database" : "file not openable"
      console.log(`${label}: panel ${shown} ms; ${kind}; screenshot ${await shoot("panel")}; API: ${calls.join(", ") || "none seen"}`)
      continue
    }
    const which = (await button.textContent()).trim()
    const t1 = Date.now()
    // the page's own time from the press to the first progress panel or data, measured inside the page (no
    // round trips to this script), next to the script's wall-clock times below
    const inPage = page.evaluate(() => new Promise((resolve) => {
      const section = document.querySelector('section[aria-label="Source database"]')
      const btn = [...(section?.querySelectorAll("button") ?? [])].find((b) => /^Open source (row|database)$/.test(b.textContent?.trim() ?? ""))
      if (!section || !btn) return resolve(null)
      const start = performance.now()
      let progress = null
      const tick = () => {
        const now = performance.now()
        if (progress === null && section.querySelector('[role="status"]')) progress = Math.round(now - start)
        if (section.querySelector('[data-testid="source-database"], [role="alert"]')) return resolve({ progress, data: Math.round(now - start) })
        if (now - start > 60000) return resolve({ progress, data: null })
        requestAnimationFrame(tick)
      }
      btn.click()
      requestAnimationFrame(tick)
    }))
    const progress = panel.getByRole("status").or(panel.getByText(/Opening|Copying|Reading/)).first()
    const data = panel.getByText(/by Loupe's read-only viewer; this is the file's content, not the report's record\./)
    const refused = panel.getByRole("alert")
    const own = await inPage
    const first = await Promise.race([
      progress.waitFor({ timeout: 10000 }).then(() => "progress"),
      data.waitFor({ timeout: 10000 }).then(() => "data"),
      refused.waitFor({ timeout: 10000 }).then(() => "refused"),
    ]).catch(() => null)
    const firstMs = Date.now() - t1
    const end = await Promise.race([
      data.waitFor({ timeout: 60000 }).then(() => "data"),
      refused.waitFor({ timeout: 60000 }).then(() => "refused"),
    ]).catch(() => "nothing within 60 s")
    const endMs = Date.now() - t1
    const rowTable = await panel.getByRole("table", { name: "Source row" }).count()
    const ok = own !== null && own.data !== null && (own.progress ?? own.data) <= 2000 && own.data <= 10000
    if (!ok) failures += 1
    console.log(`${label}: panel ${shown} ms; pressed "${which}"; first ${first} at ${firstMs} ms; ${end} at ${endMs} ms; ` +
      `in the page: progress ${own?.progress ?? "not seen"} ms, data ${own?.data ?? "not seen"} ms; ` +
      `source row table ${rowTable ? "shown" : "not shown"}; ${ok ? "within standard" : "OUTSIDE STANDARD"}; screenshot ${await shoot("opened")}; ` +
      `API: ${calls.join(", ") || "none seen"}`)
  }
  console.log(`page errors: ${errors.length}${errors.length ? " (" + errors.join(" | ") + ")" : ""}`)
} finally {
  await browser.close()
}
process.exit(failures ? 1 : 0)
