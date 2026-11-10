#!/usr/bin/env node
// The demo case's answer-key walk (lx-demo E): signed in once with the jobs login over plain http, it reads each entry
// of evidence-engine/tests/phone/planted-truths.json from the module(s) that should show it, through the same API the
// screens use, and scores each check found / missed / wrong (a link to a decoy is wrong, never noise). Then it asks the
// agent the key's questions and scores each answer against its expected words. Never tuned to pass: a check reads
// what the product shows and compares it with the key. Prints a table per module and writes the full result.
//   node journeys/live-demo-key.mjs --out <file.json> [--only F01,F02] [--no-agent]
import { readFileSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const out = arg("out")
if (!out) {
  console.error("usage: --out <file.json> [--only F01,F02] [--no-agent]")
  process.exit(2)
}
const only = arg("only") ? new Set(arg("only").split(",")) : null
const KEY = JSON.parse(readFileSync(new URL("../../evidence-engine/tests/phone/planted-truths.json", import.meta.url)))
const C = CASES.demo
// invented places of the story (demo_case.py)
const P = {
  garage: [39.261512, -76.689034], kellApt: [39.26684, -76.679512], warehouse: [39.220478, -76.660215],
  storage: [39.317206, -76.553018], home: [39.276044, -76.701233], towN2: [39.438012, -76.810544],
  hospital: [39.288503, -76.623911], bigbox: [39.310522, -76.744809], breakdown: [39.24021, -76.645522],
  tow10: [39.252204, -76.71201], tow12: [39.281533, -76.66842],
}
const metres = ([a, b], [c, d]) => {
  const r = Math.PI / 180, x = (d - b) * r * Math.cos(((a + c) / 2) * r), y = (c - a) * r
  return Math.sqrt(x * x + y * y) * 6371000
}
const near = (o, place, m = 250) => o.lat != null && metres([o.lat, o.lon], P[place]) <= m

const login = readLogin()
const browser = await chromium.launch()
const { context } = await signIn(browser, login)
const page = await context.newPage()
await page.goto(`${login.url}/cases/${C}`, { waitUntil: "domcontentloaded" })
if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
const req = async (method, path, body) => page.evaluate(async ([m, p, b]) => {
  for (let tryNo = 0; tryNo < 2; tryNo += 1) {
    const r = await fetch(p, { method: m, credentials: "include", headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined })
    if (r.status >= 500 && tryNo === 0) { await new Promise((d) => setTimeout(d, 30000)); continue }
    const t = await r.text()
    let j = null
    try { j = JSON.parse(t) } catch { j = t.slice(0, 300) }
    return { status: r.status, body: j }
  }
}, [method, path, body])
const get = async (p) => (await req("GET", p)).body
const post = async (p, b) => (await req("POST", p, b)).body
const q = (o) => new URLSearchParams(o).toString()

// ---- shared reads ------------------------------------------------------------------------------------------------
const phones = (await get(`/api/phones?case_id=${C}`)).phones || []
const PH = {} // PH1..PH6 -> phone
for (const p of phones) { const m = /PH(\d)/.exec(p.device?.model || ""); if (m) PH[`PH${m[1]}`] = p }
const labelOf = Object.fromEntries(Object.entries(PH).map(([k, p]) => [p.label, k]))
const subject = (ph) => encodeURIComponent(JSON.stringify({ kind: "extraction", extraction_id: PH[ph]?.extraction_id }))
const placesCache = {}
const places = async (ph, start, end) => {
  const k = `${ph}${start}${end}`
  if (!placesCache[k]) {
    const all = []
    let cursor = ""
    for (let i = 0; i < 20; i += 1) {
      const r = await get(`/api/pattern/${C}/places?subject=${subject(ph)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}${cursor ? `&cursor=${cursor}` : ""}`)
      all.push(...(r?.observations || []))
      if (!r?.next_cursor) break
      cursor = encodeURIComponent(r.next_cursor)
    }
    placesCache[k] = all
  }
  return placesCache[k]
}
const ledgerRows = []
for (let offset = 0; offset < 5000; offset += 500) {
  const r = await get(`/api/financial/ledger?case_id=${C}&limit=500&offset=${offset}`)
  const t = r?.transactions || []
  ledgerRows.push(...t)
  if (t.length < 500) break
}
const ledger = (re) => ledgerRows.filter((t) => re.test(`${t.description || ""} ${t.counterparty_raw || ""}`))
const amount = (t) => Math.abs(Number(t.amount_minor) / 100)
const search = async (text, group) => {
  const r = await get(`/api/search?${q({ case_id: C, q: text, ...(group ? { groups: group } : {}) })}`)
  return r?.groups || []
}
const hits = async (text, group) => (await search(text, group)).reduce((n, g) => n + (g.total || 0), 0)
const msgPhones = async (text) => {
  const g = (await search(text, "messages")).find((x) => x.group === "messages")
  return new Set((g?.items || []).map((i) => labelOf[i.phone_label] || i.phone_label))
}
const docHits = async (text) => (await search(text, "documents")).reduce((n, g) => n + (g.total || 0), 0)
const timeline = async (start, end) => (await get(`/api/timeline?${q({ case_id: C, start_date: start, end_date: end, limit: 500 })}`))?.events || []
const graphFind = async (name) => ((await get(`/api/graph/search?${q({ q: name, case_id: C, limit: 20 })}`))?.nodes || [])
  .filter((n) => (n.name || "").toLowerCase().includes(name.toLowerCase()))
const neighbourNames = async (name) => {
  const names = new Set()
  for (const n of (await graphFind(name)).slice(0, 3)) {
    const r = await get(`/api/graph/node/${encodeURIComponent(n.key)}/neighbours?case_id=${C}&depth=1`)
    for (const x of r?.nodes || []) names.add(x.name)
  }
  return [...names]
}
const identities = async (qs) => (await get(`/api/phones/identities?${q({ case_id: C, q: qs, limit: 50 })}`))?.items || []
const streamRows = async (ph, text) => {
  const filter = { case_id: C, phones: ph ? [PH[ph].extraction_id] : [], threads: [], text: { query: text, exact_characters: false }, deleted_states: [], kinds: [], collapse_copies: false }
  const idx = await post("/api/phones/streams/index", filter)
  if (!idx?.snapshot) return []
  const rows = []
  for (const d of idx.items || []) {
    const w = await post("/api/phones/streams/window", { filter, snapshot: idx.snapshot, day: d.day, offset: 0, limit: 200 })
    rows.push(...(w?.items || []))
  }
  return rows
}

// ---- scoring --------------------------------------------------------------------------------------------------------
const results = []
const score = (id, module, result, detail) => {
  results.push({ id, module, result, detail })
  console.log(`${id.padEnd(4)} ${module.padEnd(16)} ${result.padEnd(6)} ${detail}`)
}
const found = (id, module, ok, detail, wrong = false) => score(id, module, wrong ? "wrong" : ok ? "found" : "missed", detail)
const night = (d1, h1, d2, h2) => [`${d1}T${h1}:00-04:00`, `${d2}T${h2}:00-04:00`]

const checks = {
  async F01() {
    const r = ledger(/KELL T BAY 4 RENT/)
    found("F01", "financial", r.length === 9 && r.every((t) => amount(t) === 650), `${r.length} of 9 bay-rent credits at $650 (Oct 2023-Jun 2024)`)
    found("F01", "documents", (await docHits("Rent: $650.00 a month")) > 0, `lease found by its rent line: ${await docHits("Rent: $650.00 a month")} hits`)
    const t = await timeline("2023-09-27", "2023-10-02")
    found("F01", "timeline", t.length > 0, `${t.length} timeline events 27 Sep-2 Oct 2023`)
  },
  async F02() {
    const out = ledger(/ACH RUIZ AUTO & TIRE BAY 4 RENT/), into = ledger(/KELL T BAY 4 RENT/).filter((t) => t.transaction_date >= "2024-01-01")
    found("F02", "financial", out.length === 6 && into.length === 6, `${out.length} of 6 debits on Kell's account, ${into.length} of 6 credits on the shop's`)
    const n = await neighbourNames("Travis Kell")
    found("F02", "graph", n.some((x) => /Ruiz Auto/i.test(x)), `Travis Kell's graph neighbours include Ruiz Auto & Tire: ${n.some((x) => /Ruiz Auto/i.test(x))}`)
  },
  async F03() {
    found("F03", "phones", (await msgPhones("Hobbet Mill past the reservoir")).has("PH1"), "Vint's message on Mateo's phone")
    const o = await places("PH1", ...night("2024-04-12", "23:00", "2024-04-13", "01:00"))
    found("F03", "pattern_of_life", o.some((x) => near(x, "towN2")), `${o.filter((x) => near(x, "towN2")).length} positions at the tow site 23:00-01:00`, o.some((x) => near(x, "warehouse")))
    found("F03", "financial", ledger(/VINT H TOW INV 1187/).length === 1, "Vint's $185 payment")
    found("F03", "documents", (await docHits("Cleared 01:15")) > 0, "tow invoice 1187 found")
    const t = await timeline("2024-04-12", "2024-04-13")
    found("F03", "timeline", t.some((e) => /tow|Vint/i.test(`${e.name} ${e.summary}`)), `${t.length} events 12-13 Apr; a tow event: ${t.some((e) => /tow|Vint/i.test(`${e.name} ${e.summary}`))}`)
  },
  async F04() {
    found("F04", "phones", (await msgPhones("estamos en urgencias")).has("PH1"), "Spanish message to his mother on Mateo's phone")
    const o = await places("PH1", ...night("2024-05-03", "23:00", "2024-05-04", "03:30"))
    found("F04", "pattern_of_life", o.some((x) => near(x, "hospital")), `${o.filter((x) => near(x, "hospital")).length} positions at the hospital`, o.some((x) => near(x, "warehouse")))
    const media = o.filter((x) => near(x, "hospital") && (x.kind === "media" || /camera/.test(x.presence_basis || "")))
    found("F04", "media", media.some((x) => /camera/.test(x.presence_basis || "")), `photo at the hospital as presence: ${media.map((x) => x.presence_basis || x.kind).join(",") || "none"}`)
    found("F04", "financial", ledger(/FERROWMERE MEDICAL CENTER/).length === 1, "ED co-pay")
    found("F04", "documents", (await docHits("Discharged 4 May 2024")) > 0, "discharge paper found")
    const t = await timeline("2024-05-03", "2024-05-04")
    found("F04", "timeline", t.some((e) => /emergency|discharg|Ferrowmere|hospital/i.test(`${e.name} ${e.summary}`)), `${t.length} events 3-4 May`)
  },
  async F05() {
    const ids = [...(await identities("5550141")), ...(await identities("5550142"))]
    const onPH1 = ids.filter((i) => (i.phones || []).some((p) => labelOf[p.phone_label] === "PH1"))
    found("F05", "phones", true, `Okafor's numbers seen on Mateo's phone: ${onPH1.length}`, onPH1.length > 0)
    const n = await neighbourNames("Mateo Ruiz")
    found("F05", "graph", true, `Mateo Ruiz linked to Okafor in the graph: ${n.some((x) => /Okafor/i.test(x))}`, n.some((x) => /Okafor/i.test(x)))
  },
  async F06() { await coloc("F06", "PH1", "PH4", "2024-05-18", "2024-05-18", ["weak", "faint"]) },
  async F07() {
    const s = await msgPhones("car died on Ferrow Ave")
    found("F07", "phones", s.has("PH1") && s.has("PH2"), `the 8 June message on ${[...s].join(",")}`)
    found("F07", "documents", (await docHits("rode in the tow truck cab")) > 0, "tow invoice 1242 found")
    const t = await timeline("2024-06-08", "2024-06-08")
    found("F07", "timeline", t.length > 0, `${t.length} events on 8 June`)
  },
  async F08() { await coloc("F08", "PH3", "PH2", "2024-05-23", "2024-06-07", ["strong", "moderate"], 14) },
  async F09() {
    const o = (await places("PH3", "2024-06-08T12:00:00-04:00", "2024-06-15T00:00:00-04:00")).filter((x) => x.lat != null)
    const onJobs = o.filter((x) => ["garage", "breakdown", "tow10", "tow12"].some((p) => near(x, p)))
    found("F09", "pattern_of_life", o.length >= 7 && onJobs.length === o.length, `${onJobs.length} of ${o.length} positions after 8 June at the tow truck's jobs`)
  },
  async F10() {
    const r = await get(`/api/pattern/${C}/availability?subject=${subject("PH2")}&start=${encodeURIComponent("2024-03-01T00:00:00Z")}&end=${encodeURIComponent("2024-06-10T00:00:00Z")}`)
    const pieces = (r?.extractions || []).flatMap((e) => e.pieces || [])
    let covered = 0
    for (const [, d] of [["N1", "2024-03-15"], ["N2", "2024-04-12"], ["N3", "2024-05-03"], ["N4", "2024-05-17"], ["N5", "2024-05-31"]]) {
      const a = Date.parse(`${d}T23:30:00-04:00`), b = a + 4 * 3600e3
      if (pieces.some((p) => /no_data|powered_off/.test(p.state) && Date.parse(p.start) <= a && Date.parse(p.end) >= b)) covered += 1
    }
    found("F10", "pattern_of_life", covered === 5, `${covered} of 5 theft-night gaps shown as no data or powered off`)
  },
  async F11() {
    const rows = await streamRows("PH2", "tonight. 11. same as before")
    const first = rows.map((x) => x.time?.instant ?? x.time).filter(Boolean).sort()[0]
    found("F11", "phones", first === undefined ? false : true, `first 'tonight' message at ${first} (key: 2024-03-15T20:10Z)`, first !== undefined && !String(first).startsWith("2024-03-15T20:10"))
  },
  async F12() {
    const kell = await streamRows("PH2", "left something in the tow truck")
    const dee = await streamRows("PH4", "left something in the tow truck")
    const del = kell.some((x) => (x.flags || []).includes("Deleted"))
    found("F12", "phones", del && dee.length > 0 && !dee.some((x) => (x.flags || []).includes("Deleted")), `Kell's copy deleted: ${del}; Okafor's copy intact: ${dee.length > 0}`)
    found("F12", "search", (await hits("left something in the tow truck", "messages")) >= 2, "found by search")
  },
  async F13() {
    found("F13", "search", (await hits("price list", "emails")) > 0, "price-list e-mail found by search")
    const n = await neighbourNames("Gary Penn")
    found("F13", "graph", n.some((x) => /Kell/i.test(x)), `Gary Penn linked to Kell in the graph: ${n.some((x) => /Kell/i.test(x))}`)
  },
  async F14() {
    found("F14", "phones", (await hits("deposit of $9,900.00")) > 0, "bank alert on Kell's phone found")
    found("F14", "financial", ledger(/CASH DEPOSIT BR 031/).some((t) => amount(t) === 9900), "matching statement row")
  },
  async F15() {
    const r = ledger(/^CASH DEPOSIT/)
    const right = r.filter((t) => [9800, 9650, 9900, 9750, 9850].includes(amount(t)))
    found("F15", "financial", right.length === 5 && r.length === 5, `${right.length} of 5 deposits under $10,000 read at their amounts (${r.length} rows)`)
  },
  async F16() {
    const r = ledger(/POCKETWIRE TO LENA MARSH/)
    found("F16", "financial", r.length === 5, `${r.length} of 5 payments of $500 to Marsh`)
    found("F16", "phones", (await hits("You received $500.00 from Travis K.")) >= 5, `${await hits("You received $500.00 from Travis K.")} received alerts on Marsh's phone`)
  },
  async F17() {
    found("F17", "financial", ledger(/POCKETWIRE TO DESMOND OKAFOR/).length === 5, `${ledger(/POCKETWIRE TO DESMOND OKAFOR/).length} of 5 payments to Okafor`)
    const n = await neighbourNames("Desmond Okafor")
    found("F17", "graph", n.some((x) => /Kell/i.test(x)), `Okafor linked to Kell in the graph: ${n.some((x) => /Kell/i.test(x))}`)
  },
  async F18() {
    const a = ledger(/CHECK 10\d\d TRAVIS KELL/), b = ledger(/MOBILE DEP CHK 10\d\d/)
    found("F18", "financial", a.length === 5 && b.length === 5, `${a.length} of 5 checks out of Penn's account, ${b.length} of 5 deposits on Kell's`)
  },
  async F19() {
    found("F19", "financial", ledger(/STOWELL SELF STORAGE/).length === 5, `${ledger(/STOWELL SELF STORAGE/).length} of 5 storage payments on Kell's account`)
    found("F19", "documents", (await docHits("cardholder TRAVIS KELL")) > 0, "rental agreement found")
    found("F19", "phones", (await msgPhones("rent a unit at Stowell")).has("PH2"), "Kell's request to Brianna")
    const n = await neighbourNames("Stowell Self Storage")
    found("F19", "graph", n.some((x) => /Kell|Brianna/i.test(x)), `Stowell linked to Kell or Brianna: ${n.filter((x) => /Kell|Brianna/i.test(x)).join(", ") || "no"}`)
  },
  async F20() {
    const o = await places("PH5", "2024-03-01T00:00:00Z", "2024-06-24T00:00:00Z")
    const own = o.filter((x) => near(x, "storage") && /camera/.test(x.presence_basis || ""))
    found("F20", "pattern_of_life", own.length >= 4, `${own.length} of 4 of Brianna's photos placing her at unit 212`)
    found("F20", "documents", (await docHits("TVN20-118204")) > 0, "serial found in the N1 loss list")
    found("F20", "media", (await hits("TVN20-118204", "machine_text")) > 0, `serial read from the photo: ${await hits("TVN20-118204", "machine_text")} hits`)
  },
  async F21() {
    const o = (await places("PH5", "2024-03-01T00:00:00Z", "2024-06-24T00:00:00Z")).filter((x) => near(x, "warehouse"))
    const presence = o.filter((x) => x.kind === "presence")
    found("F21", "pattern_of_life", o.some((x) => (x.attribution_flags || []).includes("received_media")), `received photos at the warehouse: ${o.length}, as presence: ${presence.length}`, presence.length > 0)
  },
  async F22() {
    found("F22", "documents", (await docHits("B-11032")) >= 2, `${await docHits("B-11032")} documents with Kell's badge`)
  },
  async F23() {
    found("F23", "documents", (await docHits("B-20417")) >= 1, "Okafor's badge in the log")
    const o = await places("PH4", ...night("2024-03-15", "23:00", "2024-03-16", "03:30"))
    found("F23", "pattern_of_life", o.some((x) => near(x, "warehouse")), "Okafor's phone at the warehouse on N1")
  },
  async F24() {
    const r = await post("/api/phones/conversations/threads?sort=recent", { case_id: C, phones: [], threads: [], text: { query: "", exact_characters: false }, deleted_states: [], kinds: [], collapse_copies: true })
    const crew = (r?.items || []).filter((t) => /night crew/i.test(t.title || ""))
    const on = new Set(crew.map((t) => labelOf[t.phone?.label]))
    found("F24", "phones", on.has("PH2") && on.has("PH4"), `"night crew" on ${[...on].join(",") || "no phone"}`)
    found("F24", "search", (await hits("tonight. 11. same as before", "messages")) >= 10, `${await hits("tonight. 11. same as before", "messages")} of 10 copies found`)
  },
  async F25() {
    const s = await msgPhones("bay 4 is clear")
    found("F25", "phones", s.has("PH3"), `"bay 4 is clear" on ${[...s].join(",")}`)
    const ids = await identities("5550112")
    const onPH3 = ids.filter((i) => (i.phones || []).some((p) => labelOf[p.phone_label] === "PH3"))
    found("F25", "identities", true, `Mateo's number on the glovebox phone: ${onPH3.length}`, onPH3.length > 0)
  },
  async F26() {
    const d = (await get(`/api/dossiers?case_id=${C}`))?.dossiers?.find((x) => x.display_name === "Desmond Okafor")
    const r = d ? await get(`/api/phones/people/${d.id}/phones?case_id=${C}`) : null
    const ph = new Set((r?.phones || []).map((p) => labelOf[p.label]))
    // Linking a number to a person is a person's decision; the job never confirms one. The product's part is to
    // offer the dossier's numbers as suggestions, so a dossier showing them counts, labelled as awaiting a person.
    const suggested = r?.suggested_identities || 0
    found("F26", "dossiers", ph.size >= 3 || suggested >= 2,
      `Okafor's dossier reaches ${ph.size} phones by confirmed links; ${suggested} identities suggested, awaiting a person`)
    const names = [...(await identities("5550141")), ...(await identities("5550142"))].flatMap((i) => (i.names || []).map((n) => n.name))
    found("F26", "identities", ["Dee", "D.O."].every((n) => names.includes(n)), `names seen for his numbers: ${[...new Set(names)].join(" | ")}`)
  },
  async F27() {
    const ids = await identities("5550181")
    const linked = ids.map((i) => i.person?.display_name).filter(Boolean)
    found("F27", "identities", ids.length > 0, `Mateo Garza's number linked to: ${linked.join(",") || "nobody"}`, linked.some((n) => /Ruiz/i.test(n)))
    const n = await neighbourNames("Mateo Garza")
    found("F27", "graph", true, `Mateo Garza linked to Mateo Ruiz: ${n.some((x) => /Ruiz/i.test(x))}`, n.some((x) => /Ruiz/i.test(x)))
  },
  async F28() {
    const n = await neighbourNames("Carla Ruiz")
    found("F28", "graph", true, `Carla Ruiz linked to: ${n.filter((x) => /Mateo|Lucía|Rosa/i.test(x)).join(",") || "none of the family"}`, n.some((x) => /Mateo|Lucía|Rosa/i.test(x)))
  },
  async F29() {
    const ids = await identities("5550131")
    const linked = ids.map((i) => i.person?.display_name).filter(Boolean)
    found("F29", "identities", true, `the recycled number linked to: ${linked.join(",") || "nobody"}`, linked.some((n) => /Curtis|Kell|Ruiz/i.test(n)))
    const n = await neighbourNames("Curtis Fallowby")
    found("F29", "graph", true, `Curtis Fallowby linked to Kell or Mateo: ${n.some((x) => /Kell|Mateo/i.test(x))}`, n.some((x) => /Kell|Mateo/i.test(x)))
  },
  async F30() {
    found("F30", "phones", (await msgPhones("I'll say I saw a tow truck")).has("PH6"), "Marsh's text to her sister")
    found("F30", "documents", (await docHits("Nobody pays me except the guard company")) > 0, "her denial in the interview")
  },
  async F31() {
    const d = (await get(`/api/dossiers?case_id=${C}`))?.dossiers?.find((x) => x.display_name === "Travis Kell")
    const ai = d ? await get(`/api/workspace/${C}/ai-outputs?target_type=dossier&target_id=${d.id}`) : null
    const items = ai?.items || ai?.outputs || []
    found("F31", "interviews", items.length > 0, `AI outputs on Kell's dossier: ${items.length}`)
    found("F31", "documents", (await docHits("Never rented storage")) > 0, "proffer found")
  },
  async F32() { found("F32", "documents", (await docHits("Wexmoor Court")) > 0, "the sector note naming Kell's address") },
  async F33() { found("F33", "documents", (await docHits("second handset recovered")) > 0, "E-7 in the discovery index") },
  async F34() {
    found("F34", "financial", ledger(/^PENN'S USED TOOLS/).length === 1 && ledger(/CARD SALE M RUIZ/).length === 1, "Mateo's $240 purchase on both sides")
    found("F34", "documents", (await docHits("TVN20-099812")) >= 2, `${await docHits("TVN20-099812")} documents with the garage drill's serial`)
  },
  async F35() { found("F35", "search", (await docHits("TVN20-118207")) >= 2, `${await docHits("TVN20-118207")} documents with a listed stolen serial`) },
  async F36() {
    const r = await get(`/api/financial/statement-import/review/queue?case_id=${C}&page_list=copies`)
    const copies = (r?.copies || []).length + (r?.copy_files || []).length + (r?.set_aside_files || []).filter((f) => f.reason === "copy").length
    found("F36", "financial", copies > 0 && ledger(/CASH DEPOSIT BR 022/).length === 1, `copies set aside: ${copies}; April deposit rows: ${ledger(/CASH DEPOSIT BR 022/).length}`, ledger(/CASH DEPOSIT BR 022/).length > 1)
  },
  async F37() {
    const checksR = await get(`/api/financial/statement-checks?case_id=${C}`)
    const may = (checksR?.items || []).filter((i) => /kell-2024-05/.test(i.filename || ""))
    // A statement held for a person sits in the review queue's waiting list, not in the checks list.
    const q = await get(`/api/financial/statement-import/review/queue?case_id=${C}&page_list=waiting`)
    const waiting = (q?.items || []).filter((i) => /kell-2024-05/.test(i.filename || ""))
    const shown = [...may.map((i) => i.recorded_status), ...waiting.map((i) => `waiting (${(i.reasons || []).join("+")})`)]
    found("F37", "financial", shown.length > 0 && may.every((i) => i.recorded_status !== "balanced"), `May statement: ${shown.join(",") || "not found"}`, may.some((i) => i.recorded_status === "balanced"))
  },
  async F38() {
    const r = ledger(/CASH DEPOSIT BR 014/)
    found("F38", "financial", r.some((t) => amount(t) === 9800), `18 March deposit read as ${r.map(amount).join(",") || "nothing"}`)
  },
  async F39() {
    const items = []
    for (let offset = 0; offset < 200; offset += 25) {
      const r = await get(`/api/financial/statement-checks?case_id=${C}&offset=${offset}`)
      items.push(...(r?.items || []))
      if (!r?.has_more) break
    }
    const balanced = items.filter((i) => i.recorded_status === "balanced").length
    found("F39", "financial", balanced >= 20, `${balanced} of 20 statements balanced (${items.length} periods)`)
  },
  async F40() { found("F40", "transcripts", (await hits("other phone")) > 0, `voice note words found: ${await hits("other phone")}`) },
  async F41() {
    let n = 0
    for (const d of ["2024-03-15", "2024-04-12", "2024-05-03", "2024-05-17", "2024-05-31"]) {
      const next = new Date(Date.parse(d) + 86400e3).toISOString().slice(0, 10)
      if ((await timeline(d, next)).some((e) => /theft|stolen|Brightwater/i.test(`${e.name} ${e.summary}`))) n += 1
    }
    found("F41", "timeline", n === 5, `${n} of 5 theft nights on the timeline`)
  },
  async F42() {
    const n = await neighbourNames("Travis Kell")
    const want = [/Stowell/i, /Marsh/i, /Okafor/i, /Penn/i]
    const got = want.filter((re) => n.some((x) => re.test(x))).length
    found("F42", "graph", got === 4, `${got} of 4 of Kell's links (storage, Marsh, Okafor, Penn's)`)
  },
  async F43() {
    const o = await places("PH3", "2024-05-23T00:00:00-04:00", "2024-06-08T00:00:00-04:00")
    found("F43", "pattern_of_life", o.some((x) => near(x, "kellApt")), `${o.filter((x) => near(x, "kellApt")).length} glovebox-phone positions at Kell's apartment`, o.some((x) => near(x, "garage")))
  },
  async W01() {
    const t = (await get(`/api/workspace/${C}/tasks`))?.tasks || []
    const d = (await get(`/api/cases/${C}/deadlines`))?.deadlines || []
    const pins = (await get(`/api/workspace/${C}/pinned`))?.pinned_items || []
    found("W01", "workspace", t.length >= 3 && pins.length >= 1, `${t.length} tasks, ${pins.length} pinned`)
    found("W01", "deadlines", d.length >= 1, `${d.length} deadlines`)
  },
  async W02() {
    const e = (await get(`/api/workspace/${C}/entries?entry_type=theory`))?.entries || []
    found("W02", "theories", e.length >= 3, `${e.length} theories`)
  },
  async W03() {
    const d = (await get(`/api/dossiers?case_id=${C}`))?.dossiers || []
    found("W03", "dossiers", d.length >= 6, `${d.length} dossiers`)
  },
  async D01() {
    const n = [...(await neighbourNames("Rosa Ruiz")), ...(await neighbourNames("Lucía Ruiz"))]
    found("D01", "graph", true, `Rosa or Lucía linked to Carla Ruiz: ${n.some((x) => /Carla/i.test(x))}`, n.some((x) => /Carla/i.test(x)))
  },
}

// graded co-location between two phones from the phone-analysis run (device_users)
let runResults = null
async function coloc(id, a, b, from, to, expect, minDays = 1) {
  if (runResults === null) {
    runResults = []
    const run = await post("/api/phone-analysis/runs", { case_id: C, approach: "device_users", parameters: {} })
    const rid = run?.id || run?.run_id
    for (let i = 0; rid && i < 60; i += 1) {
      const s = await get(`/api/phone-analysis/runs/${rid}?case_id=${C}`)
      if (/complete|done|finished|failed/.test(s?.status || "")) break
      await page.waitForTimeout(10000)
    }
    for (let offset = 0; rid && offset < 5000; offset += 200) {
      const r = await get(`/api/phone-analysis/runs/${rid}/results?case_id=${C}&kind=co_location&limit=200&offset=${offset}`)
      runResults.push(...(r?.items || []))
      if ((r?.items || []).length < 200) break
    }
  }
  // One result per pair of phones over the whole period, named by phone label, with quarter-hour bins (UTC starts).
  // The key's window is in Baltimore dates, so each bin is dated in America/New_York before it is compared.
  const pair = runResults.filter((r) => { const p = (r.measures?.phones || []).map((l) => labelOf[l]); return p.includes(a) && p.includes(b) })
  const localDate = (iso) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date(iso))
  const together = pair.flatMap((r) => (r.measures?.bins || []).filter((x) => x.verdict === "together").map((x) => localDate(x.start)))
  const days = new Set(together.filter((d) => d >= from && d <= to)).size
  const strengths = pair.map((r) => r.strength)
  const wrong = expect.includes("weak") && strengths.some((s) => s === "strong" || s === "moderate")
  found(id, "pattern_of_life", pair.length > 0 && !wrong && strengths.some((s) => expect.includes(s)) && days >= minDays,
    `${a}-${b} ${from}..${to}: graded ${[...new Set(strengths)].join(",") || "none"}, together on ${days} days in the window; run total ${runResults.length}`, wrong)
}

for (const e of KEY.entries) {
  if (only && !only.has(e.id)) continue
  if (!checks[e.id]) { score(e.id, "(none)", "missed", "no check written"); continue }
  try { await checks[e.id]() } catch (err) { score(e.id, "(error)", "missed", String(err?.message || err).slice(0, 200)) }
}

// ---- agent ----------------------------------------------------------------------------------------------------------
const agent = []
if (!process.argv.includes("--no-agent") && !only) {
  for (const a of KEY.agent_questions) {
    const t0 = Date.now()
    const r = await req("POST", "/api/agent/messages", { message: a.question, case_id: C })
    const text = String(r.body?.answer || "")
    const hit = a.expect.filter((w) => text.toLowerCase().includes(w.toLowerCase()))
    const bad = a.must_not.filter((w) => text.toLowerCase().includes(w.toLowerCase()))
    const cites = r.body?.citation_check || {}
    const res = r.status !== 200 ? "missed" : bad.length ? "wrong" : hit.length === a.expect.length && (cites.ok || 0) > 0 ? "found" : "missed"
    agent.push({ id: a.id, status: r.status, result: res, expected: `${hit.length}/${a.expect.length}`, wrong_words: bad, citations: cites, thread_id: r.body?.thread_id, seconds: Math.round((Date.now() - t0) / 1000), answer: text.slice(0, 1500) })
    console.log(`${a.id.padEnd(4)} agent            ${res.padEnd(6)} words ${hit.length}/${a.expect.length}, citations ok ${cites.ok ?? "?"} of ${cites.total ?? "?"}, ${Math.round((Date.now() - t0) / 1000)} s`)
  }
}

await browser.close()
const table = {}
for (const r of results) {
  table[r.module] ??= { found: 0, missed: 0, wrong: 0 }
  table[r.module][r.result] += 1
}
console.log("\nmodule            found missed wrong")
for (const [m, v] of Object.entries(table).sort()) console.log(`${m.padEnd(17)} ${String(v.found).padStart(5)} ${String(v.missed).padStart(6)} ${String(v.wrong).padStart(5)}`)
const ag = { found: agent.filter((a) => a.result === "found").length, of: agent.length, wrong: agent.filter((a) => a.result === "wrong").length }
console.log(`agent: ${ag.found} of ${ag.of} answered as the key says, ${ag.wrong} wrong`)
writeFileSync(out, JSON.stringify({ at: new Date().toISOString(), case: C, phones: Object.fromEntries(Object.entries(PH).map(([k, p]) => [k, { label: p.label, state: p.state, counts: p.counts }])), ledger_rows: ledgerRows.length, results, table, agent, agent_score: ag }, null, 1))
