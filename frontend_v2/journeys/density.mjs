#!/usr/bin/env node
// Info density per screen (lx-style correction, Neil 2 Nov: "more variety of colours when needed on certain screens
// where there's a lot of info"). View only, no writes, signed in once with the jobs login over plain http.
//   node journeys/density.mjs --state <signed-in-state.json> --out <file.json>
// For each screen at 1440x900 it counts, inside <main> and in the first viewport only: visible text items (leaf
// elements with text), table/grid rows, chips (badge-like small rounded elements), chart marks (svg shapes and
// canvases), and the number of distinct non-grey text/fill colours already used. Counts only; never page text and
// never a screenshot (real cases are read here too).
import { readFileSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin } from "./lib.mjs"

const arg = (n) => {
  const i = process.argv.indexOf(`--${n}`)
  return i > 0 ? process.argv[i + 1] : undefined
}
const login = readLogin()
const saved = JSON.parse(readFileSync(arg("state"), "utf8"))
const D5 = "d5b330d1-b3fe-4b03-8539-98d9cc3115e0"
const T = CASES.training
const P = CASES.phonesOnly
const SCREENS = [
  ...["graph", "timeline", "map", "table", "financial", "cellebrite", "profiles", "dossiers", "evidence", "workspace", "reports"].map((v) => [`training/${v}`, `/cases/${T}/${v}`, null]),
  ["training/financial-transactions", `/cases/${T}/financial`, "Transactions"],
  ["phones/summary", `/cases/${P}/phones-prototype/summary?phone-prototype=on`, null],
  ["phones/cellebrite", `/cases/${P}/cellebrite`, null],
  ["phones/timeline", `/cases/${P}/timeline`, null],
  ["d5/financial-overview", `/cases/${D5}/financial`, null],
  ["d5/financial-transactions", `/cases/${D5}/financial`, "Transactions"],
  ["d5/table", `/cases/${D5}/table`, null],
  ["d5/timeline", `/cases/${D5}/timeline`, null],
  ["d5/graph", `/cases/${D5}/graph`, null],
]
// --set extra: the screens the first count left out (Neil 2 Nov: "what other busy screens need doing").
const EXTRA = [
  ["phones/conversations", `/cases/${P}/phones-prototype/conversations?phone-prototype=on`, null],
  ["phones/needs-a-decision", `/cases/${P}/phones-prototype/needs-a-decision?phone-prototype=on`, null],
  ["top/cases", "/cases", null],
  ["top/triage", "/triage", null],
  ["d5/financial-statements", `/cases/${D5}/financial`, "Statements & accounts"],
  ["d5/financial-people", `/cases/${D5}/financial`, "People & businesses"],
  ["d5/financial-follow-money", `/cases/${D5}/financial`, "Follow money"],
  ["d5/financial-trends", `/cases/${D5}/financial`, "Trends"],
  ["d5/financial-findings", `/cases/${D5}/financial`, "Findings & Observations"],
  ["d5/evidence", `/cases/${D5}/evidence`, null],
  ["d5/workspace", `/cases/${D5}/workspace`, null],
  ["d5/chat", `/cases/${D5}/chat`, null],
  ["d5/agent", `/cases/${D5}/agent`, null],
  ["training/chat", `/cases/${T}/chat`, null],
  ["training/agent", `/cases/${T}/agent`, null],
]
const LIST = arg("set") === "extra" ? EXTRA : SCREENS

const browser = await chromium.launch()
const out = { at: new Date().toISOString(), screens: [] }
try {
  for (const [name, path, tab] of LIST) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: saved.state })
    const page = await ctx.newPage()
    const row = { name }
    try {
      await page.goto(`${login.url}${path}`, { waitUntil: "domcontentloaded", timeout: 30000 })
      if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
      await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {})
      await page.waitForTimeout(2500)
      if (tab) {
        await page.getByText(tab, { exact: true }).first().click()
        await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {})
        await page.waitForTimeout(2500)
      }
      if (new URL(page.url()).pathname.startsWith("/login")) throw new Error("signed out")
      Object.assign(
        row,
        await page.evaluate(() => {
          const root = document.querySelector("main") ?? document.body
          const vw = innerWidth
          const vh = innerHeight
          const visible = (el) => {
            const r = el.getBoundingClientRect()
            if (r.width < 1 || r.height < 1 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) return false
            const s = getComputedStyle(el)
            return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05
          }
          let text = 0
          const colours = new Set()
          const sat = (c) => {
            const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/)
            if (!m || (m[4] !== undefined && Number(m[4]) < 0.1)) return null
            const [r, g, b] = [m[1], m[2], m[3]].map(Number)
            const mx = Math.max(r, g, b)
            const mn = Math.min(r, g, b)
            return mx - mn > 40 ? `${r >> 4},${g >> 4},${b >> 4}` : null
          }
          for (const el of root.querySelectorAll("*")) {
            if (!visible(el)) continue
            const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
            if (own) text += 1
            const s = getComputedStyle(el)
            for (const c of [own ? s.color : null, s.backgroundColor]) {
              const k = c && sat(c)
              if (k) colours.add(k)
            }
          }
          const rows = [...root.querySelectorAll("tr, [role=row]")].filter(visible).length
          const chips = [...root.querySelectorAll("[data-slot=badge], .rounded-full")].filter((el) => visible(el) && el.textContent.trim() && el.getBoundingClientRect().height <= 28).length
          const marks = [...root.querySelectorAll("svg circle, svg rect, svg path, svg line, canvas")].filter((el) => visible(el) && !el.closest("button, [role=button], a")).length
          return { text_items: text, rows, chips, chart_marks: marks, hue_colours: colours.size }
        })
      )
    } catch (e) {
      row.error = String(e?.message ?? e).split("\n")[0].slice(0, 120)
    }
    await ctx.close()
    out.screens.push(row)
    console.log(JSON.stringify(row))
  }
} finally {
  await browser.close()
  writeFileSync(arg("out"), JSON.stringify(out, null, 1))
}
