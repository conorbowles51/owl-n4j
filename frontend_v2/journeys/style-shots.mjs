#!/usr/bin/env node
// Style screenshots and the "blend" measure (lx-style items A and I).
//   node journeys/style-shots.mjs --out /mnt/owl-data/tmp/lx-style/before [--only case] [--state file.json]
// Signs in once with the jobs login over plain http (asserts isSecureContext === false), then captures every case
// view on the training case and every top-level page, in light and dark, at 1440x900 and 390x844.
// The blend measure: for the 15 case views at 1440, the top 200 px are reduced to a colour histogram (8 bins per
// channel); the measure is the mean pairwise total-variation distance (0 = identical, 1 = no colour in common).
// Higher means the views are easier to tell apart. Never prints page text or the password.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { chromium } from "playwright"
import { CASES, readLogin } from "./lib.mjs"

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : undefined
}
const outDir = arg("out")
if (!outDir) {
  console.error("--out <dir> is required")
  process.exit(2)
}
const only = arg("only") // "case" | "top" | undefined
const statePath = arg("state") ?? join(outDir, "..", "signed-in-state.json")
mkdirSync(outDir, { recursive: true })

const caseId = CASES.training
export const CASE_VIEWS = [
  ["graph", "graph"],
  ["timeline", "timeline"],
  ["map", "map"],
  ["table", "table"],
  ["financial", "financial"],
  ["cellebrite", "cellebrite"],
  ["phones", "phones-prototype/summary?phone-prototype=on"],
  ["profiles", "profiles"],
  ["dossiers", "dossiers"],
  ["evidence", "evidence"],
  ["chat", "chat"],
  ["agent", "agent"],
  ["workspace", "workspace"],
  ["reports", "reports"],
  ["settings", "settings"],
]
const TOP_PAGES = [
  ["cases", "/cases"],
  ["triage", "/triage"],
  ["admin", "/admin"],
  ["admin-ai-costs", "/admin/ai-costs"],
  ["admin-users", "/admin/users"],
  ["admin-profiles", "/admin/profiles"],
  ["admin-logs", "/admin/logs"],
  ["admin-activity", "/admin/activity"],
  ["admin-speed", "/admin/speed"],
  ["admin-tasks", "/admin/tasks"],
  ["admin-updates", "/admin/updates"],
  ["settings-user", "/settings"],
  ["settings-ai", "/settings/ai"],
  ["phone-guide", "/guide/phones"],
]
const VIEWPORTS = [
  ["1440", { width: 1440, height: 900 }],
  ["390", { width: 390, height: 844 }],
]
const THEMES = ["light", "dark"]

const login = readLogin()
const browser = await chromium.launch()
const manifest = { at: new Date().toISOString(), base: login.url, case: caseId, shots: [], blend: {} }

async function signedInState() {
  if (existsSync(statePath)) {
    const saved = JSON.parse(readFileSync(statePath, "utf8"))
    if (Date.now() - (saved.savedAt ?? 0) < 6 * 3600 * 1000) return saved.state
  }
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  await page.goto(`${login.url}/login`, { waitUntil: "domcontentloaded" })
  await page.getByPlaceholder("Enter your username").fill(login.email)
  await page.getByPlaceholder("Enter your password").fill(login.password)
  await page.getByRole("button", { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 })
  const state = await ctx.storageState()
  writeFileSync(statePath, JSON.stringify({ savedAt: Date.now(), state }), { mode: 0o600 })
  await ctx.close()
  return state
}

const state = await signedInState()

async function shoot(name, path, viewport, theme, vpName) {
  const ctx = await browser.newContext({ viewport, storageState: state })
  await ctx.addInitScript((t) => {
    try {
      localStorage.setItem("owl-theme", t)
    } catch {}
  }, theme)
  const page = await ctx.newPage()
  const file = join(outDir, `${name}-${theme}-${vpName}.png`)
  let status = "ok"
  try {
    await page.goto(`${login.url}${path}`, { waitUntil: "domcontentloaded", timeout: 30000 })
    if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => (status = "network-busy-at-15s"))
    await page.waitForTimeout(1500)
    if (new URL(page.url()).pathname.startsWith("/login")) status = "signed-out"
    await page.screenshot({ path: file })
  } catch (e) {
    status = `error: ${String(e?.message ?? e).split("\n")[0].slice(0, 120)}`
  }
  const finalPath = new URL(page.url()).pathname
  await ctx.close()
  manifest.shots.push({ name, path, theme, viewport: vpName, file, status, finalPath })
  console.log(`${status === "ok" ? "OK  " : "WARN"} ${name} ${theme} ${vpName} ${status} -> ${finalPath}`)
  return file
}

/** Colour histogram of the top `rows` px of a PNG, decoded in the browser (no image library needed). */
async function topHistogram(page, file, rows = 200, bins = 8) {
  const b64 = readFileSync(file).toString("base64")
  return page.evaluate(
    async ({ b64, rows, bins }) => {
      const img = new Image()
      img.src = `data:image/png;base64,${b64}`
      await img.decode()
      const c = document.createElement("canvas")
      c.width = img.width
      c.height = Math.min(rows, img.height)
      const g = c.getContext("2d")
      g.drawImage(img, 0, 0)
      const d = g.getImageData(0, 0, c.width, c.height).data
      const h = new Array(bins * bins * bins).fill(0)
      const step = 256 / bins
      for (let i = 0; i < d.length; i += 4) {
        h[Math.floor(d[i] / step) * bins * bins + Math.floor(d[i + 1] / step) * bins + Math.floor(d[i + 2] / step)] += 1
      }
      const n = d.length / 4
      return h.map((v) => v / n)
    },
    { b64, rows, bins }
  )
}

/** Financial gate (view only, no writes): BNB2 Overview and the transactions ledger, light, 1440. The numbers on
 * them must be the same before and after. The visible text is saved beside the image for the comparison. */
async function financialGate() {
  const d5 = "d5b330d1-b3fe-4b03-8539-98d9cc3115e0"
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem("owl-theme", "light")
    } catch {}
  })
  const page = await ctx.newPage()
  await page.goto(`${login.url}/cases/${d5}/financial`, { waitUntil: "domcontentloaded", timeout: 30000 })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {})
  await page.waitForTimeout(3000)
  const numbers = (t) => (t.match(/[-+−]?[$£€]?\d[\d,]*(\.\d+)?\s?[kKmM%]?/g) ?? []).join(" ")
  await page.screenshot({ path: join(outDir, "gate-d5-overview.png") })
  writeFileSync(join(outDir, "gate-d5-overview.numbers.txt"), numbers(await page.locator("main").innerText()))
  await page.getByText("Transactions", { exact: true }).first().click()
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {})
  await page.waitForTimeout(3000)
  await page.screenshot({ path: join(outDir, "gate-d5-ledger.png") })
  writeFileSync(join(outDir, "gate-d5-ledger.numbers.txt"), numbers(await page.locator("main").innerText()))
  await ctx.close()
  console.log("GATE d5 overview + ledger captured")
}

try {
  if (only === "gate") {
    await financialGate()
    process.exit(0)
  }
  for (const [vpName, viewport] of VIEWPORTS) {
    for (const theme of THEMES) {
      if (only !== "top") for (const [name, sub] of CASE_VIEWS) await shoot(name, `/cases/${caseId}/${sub}`, viewport, theme, vpName)
      if (only !== "case") for (const [name, path] of TOP_PAGES) await shoot(name, path, viewport, theme, vpName)
    }
  }
  // Blend measure over the 15 case views at 1440, per theme.
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  for (const theme of THEMES) {
    const hs = []
    for (const [name] of CASE_VIEWS) {
      const file = join(outDir, `${name}-${theme}-1440.png`)
      if (existsSync(file)) hs.push([name, await topHistogram(page, file)])
    }
    let sum = 0
    let pairs = 0
    for (let i = 0; i < hs.length; i++)
      for (let j = i + 1; j < hs.length; j++) {
        let tv = 0
        for (let k = 0; k < hs[i][1].length; k++) tv += Math.abs(hs[i][1][k] - hs[j][1][k])
        sum += tv / 2
        pairs += 1
      }
    manifest.blend[theme] = { views: hs.length, pairs, mean_distance: pairs ? Number((sum / pairs).toFixed(4)) : null }
    console.log(`BLEND ${theme}: ${hs.length} views, ${pairs} pairs, mean distance ${manifest.blend[theme].mean_distance}`)
  }
  await ctx.close()
} finally {
  await browser.close()
  // The gate run captures only the Financial pages; it never replaces the full set's manifest.
  if (only !== "gate") writeFileSync(join(outDir, "manifest.json"), JSON.stringify(manifest, null, 1))
}
