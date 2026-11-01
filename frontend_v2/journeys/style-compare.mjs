#!/usr/bin/env node
// Before/after page for the style screenshots (lx-style item I).
//   node journeys/style-compare.mjs <dir containing before/ and after/>  ->  <dir>/compare.html
// Reads both manifests written by style-shots.mjs and lays every shot out side by side, with the blend measure.
// Image paths are relative, so the folder can be copied or served as it is.
import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const dir = process.argv[2]
if (!dir) {
  console.error("usage: style-compare.mjs <dir>")
  process.exit(2)
}
const load = (side) => JSON.parse(readFileSync(join(dir, side, "manifest.json"), "utf8"))
const before = load("before")
const after = load("after")
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c])
const key = (s) => `${s.name}-${s.theme}-${s.viewport}`
const afterBy = new Map(after.shots.map((s) => [key(s), s]))

const blendRows = ["light", "dark"]
  .map((t) => {
    const b = before.blend?.[t]?.mean_distance
    const a = after.blend?.[t]?.mean_distance
    const change = b && a ? `${(((a - b) / b) * 100).toFixed(0)}%` : "n/a"
    return `<tr><td>${t}</td><td>${b ?? "n/a"}</td><td>${a ?? "n/a"}</td><td>${change}</td></tr>`
  })
  .join("")

const groups = {}
for (const s of before.shots) (groups[`${s.viewport}-${s.theme}`] ??= []).push(s)
const sections = Object.entries(groups)
  .map(([g, shots]) => {
    const rows = shots
      .map((s) => {
        const a = afterBy.get(key(s))
        const img = (side, shot) =>
          shot ? `<a href="${side}/${esc(shot.file.split("/").pop())}"><img loading="lazy" src="${side}/${esc(shot.file.split("/").pop())}" alt="${esc(`${shot.name} ${side}`)}"></a>` : "<p>missing</p>"
        return `<div class="row"><h3>${esc(s.name)} <small>${esc(s.path)}</small></h3><div class="pair"><figure><figcaption>Before</figcaption>${img("before", s)}</figure><figure><figcaption>After</figcaption>${img("after", a)}</figure></div></div>`
      })
      .join("")
    return `<section><h2>${esc(g.replace("-", " px, "))}</h2>${rows}</section>`
  })
  .join("")

const gate = ["overview", "ledger"]
  .map(
    (n) =>
      `<div class="row"><h3>BNB2 Financial ${n} (view only)</h3><div class="pair"><figure><figcaption>Before</figcaption><img src="before/gate-d5-${n}.png" alt="before ${n}"></figure><figure><figcaption>After</figcaption><img src="after/gate-d5-${n}.png" alt="after ${n}"></figure></div></div>`
  )
  .join("")

writeFileSync(
  join(dir, "compare.html"),
  `<!doctype html><meta charset="utf-8"><title>Loupe styling: before and after</title>
<style>
body{font:14px/1.5 "IBM Plex Sans",system-ui,sans-serif;margin:24px;background:#f7f7f8;color:#15161a}
h1,h2{font-family:"Space Grotesk",system-ui,sans-serif}
table{border-collapse:collapse}td,th{border:1px solid #d9dae0;padding:4px 10px;text-align:left}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}figure{margin:0}img{width:100%;border:1px solid #d9dae0}
.row{margin:16px 0 28px}small{color:#63666e;font-weight:400}figcaption{font-weight:600}
</style>
<h1>Loupe styling: before and after</h1>
<p>Captured signed in over plain http (${esc(before.base)}) on the synthetic training case. Before: ${esc(before.at)}. After: ${esc(after.at)}.</p>
<h2>How distinct the case views are</h2>
<p>Mean colour difference between the top 200 px of the 15 case views, compared in pairs (0 = identical, 1 = nothing in common). Higher is easier to tell apart.</p>
<table><tr><th>Theme</th><th>Before</th><th>After</th><th>Change</th></tr>${blendRows}</table>
<h2>Financial: same numbers before and after</h2>${gate}
${sections}`
)
console.log(`wrote ${join(dir, "compare.html")}`)
