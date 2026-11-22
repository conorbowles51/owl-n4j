#!/usr/bin/env node
// Neil's phone-report prompt (rubric question R1) asked N times through the live API on the demo case, each answer scored
// against evidence-engine/tests/phone/planted-report-rubric.json (facts found, decoys linked, defects). Read-only for the
// case: each ask makes an agent thread, as the walk's report question does.
//   node journeys/live-phone-report-score.mjs --out <file.json> [--reps 3]
import { readFileSync, writeFileSync } from "node:fs"
import { scoreReport } from "./demo-report-score.mjs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : fallback }
const out = arg("out")
if (!out) { console.error("usage: --out <file.json> [--reps 3]"); process.exit(2) }
const reps = Number(arg("reps", "3"))
const rubric = JSON.parse(readFileSync(new URL("../../evidence-engine/tests/phone/planted-report-rubric.json", import.meta.url)))
const browser = await chromium.launch()
const login = readLogin()
const { context } = await signIn(browser, login)
const page = await context.newPage()
await page.goto(`${login.url}/cases/${CASES.demo}`, { waitUntil: "domcontentloaded" })
if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
const results = []
for (let rep = 1; rep <= reps; rep += 1) {
  const t0 = Date.now()
  const r = await page.evaluate(async ([p, b]) => {
    const x = await fetch(p, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })
    const t = await x.text(); let j = null; try { j = JSON.parse(t) } catch { j = t.slice(0, 300) }
    return { status: x.status, body: j }
  }, ["/api/agent/messages", { message: rubric.question, case_id: CASES.demo }])
  const text = String(r.body?.answer || "")
  const row = { rep, status: r.status, seconds: Math.round((Date.now() - t0) / 1000), thread_id: r.body?.thread_id, citations: r.body?.citation_check || {}, score: scoreReport(text, rubric), chars: text.length, answer: text }
  results.push(row)
  console.log(`rep ${rep}: status ${row.status} facts ${row.score.facts_found}/${row.score.facts_of} found ${row.score.facts.filter((f) => f.found).map((f) => f.id).join(" ")} decoys wrong ${row.score.decoys_wrong} dropped ${row.score.defects.dropped_names} doubled ${row.score.defects.duplicated_sections} ${row.seconds} s`)
  writeFileSync(out, JSON.stringify({ at: new Date().toISOString(), results }, null, 1))
}
await browser.close()
