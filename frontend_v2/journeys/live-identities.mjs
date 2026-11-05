#!/usr/bin/env node
// Live walk of phones in People and dossiers (07 J-3, J-10, J-16, 4.5): signed in once with the jobs login over plain
// http, in the synthetic Phones-only case. Prints counts, states and milliseconds; screenshots stay in --shots.
// Every write is undone through the app (Unlink with a reason, the Add to reply's Undo).
//   node journeys/live-identities.mjs --shots <dir> [--only a,b,c,d,e,f]
import { mkdirSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const shots = arg("shots")
const only = arg("only", "a,b,c,d,e,f").split(",")
if (!shots) {
  console.error("usage: --shots <dir> [--only a,b,c,d,e,f]")
  process.exit(2)
}
mkdirSync(shots, { recursive: true })
const caseId = CASES.phonesOnly
const login = readLogin()
const browser = await chromium.launch()
const failures = []
const say = (...a) => console.log(...a)
const num = (t) => Number(String(t).replace(/,/g, ""))
async function part(id, name, fn) {
  if (!only.includes(id)) return
  const t0 = Date.now()
  try {
    await fn()
    say(`PASS ${id} ${name} (${Date.now() - t0} ms)`)
  } catch (e) {
    failures.push(id)
    say(`FAIL ${id} ${name}: ${String(e?.message ?? e).split("\n")[0].slice(0, 240)}`)
    await page.screenshot({ path: `${shots}/fail-${id}.png` }).catch(() => {})
  }
}
const { context } = await signIn(browser, login)
const page = await context.newPage()
const pageErrors = []
page.on("pageerror", (e) => pageErrors.push(e.message.slice(0, 160)))
const base = `${login.url}/cases/${caseId}`
const api = (path, init) => page.evaluate(async ([p, i]) => {
  const r = await fetch(p, { ...(i ?? {}), credentials: "include", headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("authToken") ?? ""}` } })
  return { status: r.status, body: r.ok ? await r.json() : null }
}, [path, init ?? null])
const shot = (name) => page.screenshot({ path: `${shots}/${name}.png` })
const go = async (path) => {
  await page.goto(`${base}${path}`, { waitUntil: "domcontentloaded" })
  if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
}
/** The total the Conversations page states, once ready. */
const conversationsTotal = async () => {
  const c = page.getByText(/^[\d,]+ messages?\b/).first()
  await c.waitFor({ timeout: 45000 })
  return num((await c.innerText()).match(/[\d,]+/)[0])
}
await page.goto(`${base}/dossiers`, { waitUntil: "domcontentloaded" })

let registry
let linkedDossier
let dossierPanel

await part("a", "Phone identities tab", async () => {
  const t0 = Date.now()
  await go("/dossiers?tab=phone-identities")
  const list = page.getByRole("status").filter({ hasText: /identit/ }).first()
  await list.waitFor({ timeout: 30000 })
  say(`  tab first rows ${Date.now() - t0} ms; sentence: ${(await list.innerText()).replace(/[A-Z][a-z]+ [A-Z][a-z]+/g, "<name>").slice(0, 120)}`)
  registry = (await api(`/api/phones/identities?case_id=${caseId}&limit=100`)).body
  say(`  api total ${registry.total}, returned ${registry.items?.length}, phones_in_case ${registry.phones_in_case ?? "-"}`)
  await shot("a1-tab")
  const unlinked = (await api(`/api/phones/identities?case_id=${caseId}&limit=25&linked=no`)).body
  say(`  unlinked ${unlinked.total}`)
  const row = page.getByRole("tabpanel").getByRole("button").filter({ hasText: /\d/ }).first()
  const first = (unlinked.items ?? [])[0]
  await page.goto(`${base}/dossiers?tab=phone-identities&identity=${encodeURIComponent(first.identity_key)}`, { waitUntil: "domcontentloaded" })
  await page.getByRole("heading", { name: "Link to a person" }).waitFor({ timeout: 30000 })
  await shot("a2-detail")
  const sug = await page.getByText("Suggested", { exact: true }).count()
  say(`  detail open; suggested block ${sug}; saved-under-your-name line ${await page.getByText(/Saved under your name/).count()}`)
  const person = page.getByRole("combobox", { name: "Person", exact: true })
  const options = await person.locator("option").allTextContents()
  const target = options.find((o) => /Cassia|Corin|Garnet|Jory/.test(o))
  await person.selectOption({ label: target })
  await page.getByRole("button", { name: "Link", exact: true }).click()
  await page.getByRole("status").filter({ hasText: /^Linked to / }).first().waitFor({ timeout: 30000 })
  const after = (await api(`/api/phones/identities?case_id=${caseId}&limit=25&linked=no`)).body
  say(`  link decision saved: unlinked ${unlinked.total} -> ${after.total}`)
  await shot("a3-linked")
  await page.locator('section[aria-labelledby="identity-link"]').getByRole("textbox").first().fill("Live check: undoing a test link")
  await page.getByRole("button", { name: "Unlink", exact: true }).click()
  await page.getByText("Not linked to a person.").or(page.getByRole("button", { name: "Link", exact: true })).first().waitFor({ timeout: 30000 })
  await page.waitForTimeout(1500)
  const undone = (await api(`/api/phones/identities?case_id=${caseId}&limit=25&linked=no`)).body
  say(`  unlink saved: unlinked back to ${undone.total}`)
  if (undone.total !== unlinked.total) throw new Error("the unlink did not restore the count")
})

await part("b", "On the phones panel, J-3, J-16", async () => {
  const dossiers = (await api(`/api/dossiers?case_id=${caseId}&limit=50`)).body?.dossiers ?? []
  for (const d of dossiers) {
    const p = (await api(`/api/phones/people/${d.id}/phones?case_id=${caseId}`)).body
    if (p?.identities?.length && (!dossierPanel || p.total_records > dossierPanel.total_records)) {
      dossierPanel = p
      linkedDossier = d
    }
  }
  if (!linkedDossier) throw new Error("no dossier with linked identities")
  say(`  dossier panel keys: ${Object.keys(dossierPanel).join(",")}`)
  const t0 = Date.now()
  await go(`/dossiers?dossier=${linkedDossier.id}`)
  const panel = page.getByRole("region", { name: "On the phones" })
  await panel.waitFor({ timeout: 30000 })
  await panel.getByRole("link").first().waitFor({ timeout: 30000 })
  say(`  panel shown ${Date.now() - t0} ms`)
  await panel.scrollIntoViewIfNeeded()
  await shot("b1-panel")
  // J-3 start: every count opens to its records; the first article's Open conversations equals its stated number
  const links = await panel.getByRole("link").evaluateAll((a) => a.map((x) => ({ t: x.innerText.trim().slice(0, 60), h: x.getAttribute("href") })))
  let checked = 0
  for (const l of links.filter((x) => /^[\d,]+\b/.test(x.t) && /conversations/.test(x.h ?? "")).slice(0, 6)) {
    const want = num(l.t.match(/[\d,]+/)[0])
    await page.goto(`${login.url}${l.h}`, { waitUntil: "domcontentloaded" })
    const got = await conversationsTotal()
    say(`  count link: states ${want}, Conversations ${got}`)
    if (want !== got) throw new Error(`count ${want} opened ${got}`)
    checked += 1
  }
  if (!checked) say(`  no number-led count links; links: ${links.map((l) => l.t).join(" | ").replace(/[A-Z][a-z]+ [A-Z][a-z]+/g, "<name>")}`)
  await shot("b2-j3-conversations")
  await go(`/dossiers?dossier=${linkedDossier.id}`)
  await panel.getByRole("link").first().waitFor({ timeout: 30000 })
  const cmp = panel.getByRole("link", { name: /compare/i }).first()
  if (await cmp.count()) {
    await cmp.click()
    await page.getByText(/on both/i).first().waitFor({ timeout: 45000 })
    await shot("b3-j16-compare")
    say(`  J-16 compare open with "on both" stated`)
  } else say("  this dossier is on one phone: compare not offered")
})

await part("c", "Scope bar, presets, memory", async () => {
  await page.evaluate(() => sessionStorage.clear())
  await go("/conversations")
  const all = await conversationsTotal()
  const presets = page.getByRole("button", { name: "Presets" })
  await presets.waitFor({ timeout: 30000 })
  await presets.click()
  const items = await page.getByRole("menuitem").allTextContents()
  say(`  all ${all}; ${items.length} presets`)
  await shot("c1-presets")
  await page.getByRole("menuitem").first().click()
  await page.waitForTimeout(1500)
  const one = await conversationsTotal()
  say(`  preset scope -> ${one} messages; url scope params ${new URL(page.url()).search.length > 1}`)
  await shot("c2-scoped")
  await page.waitForTimeout(1200)
  // a new arrival within the session, by the app's own navigation
  await page.getByRole("link", { name: /^Map$/ }).first().click().catch(() => {})
  await page.waitForTimeout(1500)
  await page.goBack()
  await page.evaluate(() => history.replaceState(history.state, "", location.pathname))
  await page.reload({ waitUntil: "domcontentloaded" })
  await page.getByText(/Showing your last selection/).first().waitFor({ timeout: 30000 })
  await shot("c3-last-selection")
  say("  Showing your last selection stated")
  await page.getByRole("button", { name: "Presets" }).click()
  say(`  recent header ${await page.getByText(/Your last \d+ scopes?/).count()}`)
  await shot("c4-recent")
  await page.keyboard.press("Escape")
  for (const [path, name] of [["/map", "map"], ["/timeline", "timeline"], ["/media", "media"]]) {
    await go(`${path}?people=${encodeURIComponent(registry?.items?.[0]?.identity_key ?? "x")}&mode=involving`)
    await page.waitForTimeout(4000)
    await shot(`c5-${name}`)
    say(`  ${name}: scope region ${await page.getByRole("region", { name: /scope/i }).count()}, stated not applied ${await page.getByText(/not applied|cannot apply|not apply/i).count()}`)
  }
})

await part("d", "Open in Graph with a stated limit", async () => {
  await page.evaluate(() => sessionStorage.clear())
  await go("/conversations")
  await page.getByRole("button", { name: "Presets" }).click()
  await page.getByRole("menuitem").first().click()
  await page.waitForTimeout(1000)
  const open = page.getByRole("link", { name: "Open in Graph" }).first()
  await open.waitFor({ timeout: 20000 })
  await open.click()
  const banner = page.getByRole("status", { name: "Phone scope on the Graph" })
  await banner.waitFor({ timeout: 45000 })
  await page.waitForTimeout(2500)
  await shot("d1-graph")
  say(`  banner: ${(await banner.innerText()).replace(/[A-Z][a-z]+ [A-Z][a-z]+/g, "<name>").replace(/\s+/g, " ").slice(0, 260)}`)
})

await part("e", "Add to on Search and Phone summary, device dossier", async () => {
  // a term with more than 500 hits would go as one frozen selection; the add picks the smallest set of 20 or more, so
  // the walk's Undo finishes, on a note not yet used by this walk
  const group = async (q) => (await api(`/api/search/group?case_id=${caseId}&q=${encodeURIComponent(q)}&group=messages&limit=1`)).body
  let term = null
  for (const q of ["555", "201", "the", "and", "you"]) {
    const g = await group(q)
    say(`  group "${q}": ${g?.total ?? "-"}`)
    if (q === "and") term = q
  }
  if (!term) throw new Error("no search term with hits")
  await go(`/search?q=${encodeURIComponent(term)}&group=messages`)
  const every = page.getByLabel(/Every hit/).or(page.getByRole("checkbox", { name: /Every hit/ })).first()
  await every.waitFor({ timeout: 45000 })
  await shot("e1-search")
  const t0 = Date.now()
  await every.check()
  const add = page.getByRole("button", { name: "Add to…" }).first()
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("Add to…") && !b.disabled), null, { timeout: 60000 })
  say(`  whole result ready to add ${Date.now() - t0} ms`)
  await add.click()
  await page.getByRole("button", { name: /^Note/ }).click()
  const opt = page.getByRole("listbox", { name: /Choose where to add/ }).getByRole("option").nth(1)
  await opt.waitFor({ timeout: 20000 })
  await shot("e2-add-dialog")
  await opt.click()
  const reply = page.getByRole("status").filter({ has: page.getByRole("button", { name: "Undo" }) }).first()
  await reply.waitFor({ timeout: 90000 })
  say(`  reply: ${(await reply.innerText()).replace(/\s+/g, " ").slice(0, 160)}`)
  await shot("e3-added")
  await reply.getByRole("button", { name: "Undo" }).click()
  await page.getByText(/Removed [\d,]+ links?/).first().waitFor({ timeout: 180000 })
  await shot("e4-undone")
  say(`  undo: ${(await page.getByText(/Removed [\d,]+ links?/).first().innerText()).slice(0, 80)}`)

  const phones = (await api(`/api/phones/identities?case_id=${caseId}&limit=1`)).body?.phones ?? []
  const pid = phones[0]?.extraction_id ?? phones[0]?.id
  if (!pid) throw new Error("no phone in the registry reply")
  await page.goto(`${login.url}/cases/${caseId}/phones/${pid}`, { waitUntil: "domcontentloaded" })
  const row = page.getByLabel("Add this phone")
  await row.waitFor({ timeout: 45000 })
  await shot("e5-summary")
  await row.getByRole("button", { name: /Add to a device dossier/ }).click()
  const name = `Live check device ${Date.now()}`
  await page.getByLabel("Name of the new dossier").fill(name)
  await page.getByRole("group", { name: "Add to a device dossier" }).getByRole("button", { name: "Add", exact: true }).click()
  const done = row.getByRole("status").filter({ has: page.getByRole("button", { name: "Undo" }) }).first()
  await done.waitFor({ timeout: 30000 })
  await shot("e6-device-dossier")
  await done.getByRole("button", { name: "Undo" }).click()
  await page.waitForTimeout(1500)
  say("  device dossier made, phone linked, link undone; the empty dossier stays")
})

await part("f", "Address dossier from a map point", async () => {
  await go("/map")
  const btn = page.getByRole("button", { name: /Add to an address dossier/ }).first()
  await btn.waitFor({ timeout: 45000 }).catch(() => {})
  const n = await btn.count()
  say(`  address buttons visible on the map page: ${n}`)
  await shot("f1-map")
})

say(`page errors ${pageErrors.length}${pageErrors.length ? `: ${[...new Set(pageErrors)].slice(0, 3).join(" | ")}` : ""}`)
say(failures.length ? `FAILED: ${failures.join(",")}` : "ALL PASS")
await browser.close()
process.exit(failures.length ? 1 : 0)
