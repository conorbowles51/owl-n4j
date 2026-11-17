#!/usr/bin/env node
// Short films of the real application on the demo case, for the public site (lx-sitefilms). Signed in once with the
// jobs login over plain http, one browser context per film with Playwright's video recorder, a visible cursor ring
// injected into the page, and deliberate pacing. Read only: the films open, scroll, filter and open citations; they
// never accept, reject, save, upload or start anything that writes to the case. Every request that is not a GET is
// listed per film and must be on READ_ONLY_POSTS (view-only computations), or the film fails.
//
//   node journeys/site-films.mjs --raw <dir> [--only opening,money] [--out <result.json>]
//
// Writes <dir>/<film>.webm (the raw recording) and <dir>/<film>.json (the kept segments, in seconds from the start
// of the recording, and the poster moment). journeys/site-films-encode.py turns them into the site's files and
// reads every quarter second of each film for loading, error and sign-in text.
import { mkdirSync, renameSync, writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : fallback
}
const raw = arg("raw")
if (!raw) {
  console.error("usage: --raw <dir> [--only opening,money] [--out <result.json>]")
  process.exit(2)
}
mkdirSync(raw, { recursive: true })
const only = arg("only") ? new Set(arg("only").split(",")) : null
const C = CASES.demo
const VIEW = { width: 1440, height: 900 }

// Requests that are not GETs but only compute a view for the reader (the route needs case view, nothing is added to
// the case). Anything else that is not a GET fails the film.
const READ_ONLY_POSTS = [
  /\/api\/pattern\/[^/]+\/together$/, // "Together": the run is the reader's own (routers/pattern_of_life.py)
  /\/api\/phones\/map\/(summary|points|area)$/, // Map phone layer queries: totals, positions in view, a drawn area
  /\/api\/phones\/timeline\/(index|window|buckets)$/, // Timeline phone lens queries
  /\/api\/investigation-trail/, // the reader's own navigation history
  /\/api\/trail/,
  /\/api\/auth\/refresh/,
  /\/api\/citations\/resolve$/, // looks up what a citation link points at
  /\/api\/history\/cases\/[^/]+$/, // the reader's own "All steps" navigation history
  /\/api\/request-speed\/page-views$/, // page-speed telemetry
  /\/api\/phone-analysis\/money\/ledger-links$/, // "Also recorded on phone" for ledger rows (case view)
  /\/api\/workspace\/[^/]+\/financial-evidence-changes$/, // what changed in a finding's cited payments ("Reads only")
  /\/api\/phones\/links\/states$/, // the state of a finding's phone links ("A read")
  /\/api\/phones\/link-analysis\/edges$/, // the graph's communication and money edges (case view)
]

// The thread and record ids the films open (found on the live demo case, 15 Nov 2026).
const T = {
  rent: "dfe526e7-04f7-4fbf-96bd-8614e575855b", // "What are the $650 monthly payments into the Ruiz Auto & Tire account?"
  unit212: "1ec7b369-d3b3-491f-bdc4-59affe8a63dd", // "Who rented storage unit 212 and who paid for it?"
  deposit: "459c951a-ee55-465e-a976-3abbcb3c9076", // Kell's 18 March cash deposit, printed "9  800.00"
  warehouse: [-76.660215, 39.220478], // Brightwater Logistics, evidence-engine/tests/phone/demo_case.py WAREHOUSE
}

/** The cursor ring: follows real mouse events, so it shows exactly where the recorder points and clicks. */
const CURSOR = `(() => {
  if (window.__filmCursor) return; window.__filmCursor = true
  const add = () => {
    const s = document.createElement("style")
    s.textContent = "#film-cursor{position:fixed;left:0;top:0;width:26px;height:26px;margin:-13px 0 0 -13px;border:2.5px solid #fff;" +
      "border-radius:50%;box-shadow:0 0 0 1.5px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.45);background:rgba(229,57,70,.28);" +
      "pointer-events:none;z-index:2147483647;transition:transform .12s ease-out;will-change:left,top}" +
      "#film-cursor.down{transform:scale(.72);background:rgba(229,57,70,.6)}" +
      "#film-pulse{position:fixed;width:26px;height:26px;margin:-13px 0 0 -13px;border:2px solid rgba(229,57,70,.9);border-radius:50%;" +
      "pointer-events:none;z-index:2147483646;animation:film-pulse .55s ease-out forwards}" +
      "@keyframes film-pulse{from{transform:scale(1);opacity:1}to{transform:scale(2.6);opacity:0}}"
    document.documentElement.appendChild(s)
    const c = document.createElement("div"); c.id = "film-cursor"
    const p = JSON.parse(sessionStorage.getItem("film-cursor") || "null") || { x: 720, y: 450 }
    c.style.left = p.x + "px"; c.style.top = p.y + "px"
    document.documentElement.appendChild(c)
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"
      sessionStorage.setItem("film-cursor", JSON.stringify({ x: e.clientX, y: e.clientY })) }, true)
    addEventListener("mousedown", (e) => { c.classList.add("down"); const q = document.createElement("div"); q.id = "film-pulse"
      q.style.left = e.clientX + "px"; q.style.top = e.clientY + "px"; document.documentElement.appendChild(q); setTimeout(() => q.remove(), 600) }, true)
    addEventListener("mouseup", () => c.classList.remove("down"), true)
  }
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", add); else add()
})()`

/** One film: a page recorded from its creation, kept segments, paced pointer moves. */
async function makeFilm(browser, state, name) {
  const context = await browser.newContext({
    viewport: VIEW, deviceScaleFactor: 1, storageState: state, recordVideo: { dir: `${raw}/tmp-${name}`, size: VIEW },
  })
  await context.addInitScript(CURSOR)
  const page = await context.newPage()
  const t0 = Date.now()
  const now = () => (Date.now() - t0) / 1000
  const segments = []
  let open = null
  let mouse = { x: 720, y: 450 }
  const writes = []
  const errors = []
  page.on("request", (r) => {
    if (r.method() === "GET" || r.method() === "HEAD" || r.method() === "OPTIONS") return
    const path = new URL(r.url()).pathname
    if (!READ_ONLY_POSTS.some((re) => re.test(path))) writes.push(`${r.method()} ${path}`)
  })
  page.on("pageerror", (e) => errors.push(`pageerror: ${String(e.message).slice(0, 200)}`))
  page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${new URL(r.url()).pathname}`) })
  const f = {
    page, name, poster: null,
    show() { if (open === null) open = now() },
    hide() { if (open !== null) { segments.push([open, now()]); open = null } },
    markPoster() { f.poster = { at: now() } },
    async goto(path, ready) {
      f.hide()
      for (let attempt = 0; ; attempt++) {
        await page.goto(`${(await f.base)}/cases/${C}/${path}`, { waitUntil: "domcontentloaded", timeout: 120_000 })
        if ((await page.evaluate(() => window.isSecureContext)) !== false) throw new Error("isSecureContext was not false")
        if (/\/login/.test(page.url())) throw new Error("landed on the sign-in page")
        try {
          await ready()
          break
        } catch (e) {
          // A release restarts the backend for a minute or two: retry once after 30 s, then fail.
          const down = await page.getByText("Cannot check sign-in").isVisible().catch(() => false)
          if (attempt > 0 || !down) throw e
          await page.waitForTimeout(30_000)
        }
      }
      await settled(page)
      await page.mouse.move(mouse.x, mouse.y)
      await page.waitForTimeout(400)
      f.show()
    },
    /** Await real content; a wait longer than `min` seconds is cut out of the film (loading frames never show). */
    async until(fn, { keep = 0, min = 0.2 } = {}) {
      const a = now()
      await fn()
      await settled(page) // no loading text left anywhere on the page
      await page.waitForTimeout(150) // the recorder's frame catches up with the page
      const b = now()
      if (open !== null && b - a > min) { segments.push([open, a + keep]); open = b - 0.02 }
    },
    async pause(ms) { await page.waitForTimeout(ms) },
    async moveTo(x, y, ms = 550) {
      // Time-bounded: on a loaded box each mouse event is a round trip, so steps follow the clock, not a count.
      const from = { ...mouse }, start = Date.now()
      for (;;) {
        const k = Math.min(1, (Date.now() - start) / ms), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2
        await page.mouse.move(from.x + (x - from.x) * e, from.y + (y - from.y) * e)
        if (k >= 1) break
        await page.waitForTimeout(16)
      }
      mouse = { x, y }
    },
    async point(locator, { ms = 550, dx = 0.5, dy = 0.5 } = {}) {
      // A list that refreshes (an agent run elsewhere in the case) can redraw the element mid-step: find it again once.
      for (let attempt = 0; ; attempt++) {
        try {
          await locator.waitFor({ state: "visible", timeout: 60_000 })
          await locator.scrollIntoViewIfNeeded()
          break
        } catch (e) {
          if (attempt > 0 || !/not attached/.test(String(e?.message))) throw e
          await page.waitForTimeout(500)
        }
      }
      const b = await locator.boundingBox()
      if (!b) throw new Error("no box to point at")
      await f.moveTo(b.x + b.width * dx, b.y + b.height * dy, ms)
      return b
    },
    async click(locator, opts = {}) {
      await f.point(locator, opts)
      await page.waitForTimeout(180)
      await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up()
    },
    async clickAt(x, y, ms = 500) {
      await f.moveTo(x, y, ms)
      await page.waitForTimeout(150)
      await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up()
    },
    /** Scroll the element under the pointer in small wheel steps, so the motion reads on film. */
    async wheel(dy, { step = 90, ms = 45 } = {}) {
      const n = Math.max(1, Math.round(Math.abs(dy) / step))
      for (let i = 0; i < n; i++) { await page.mouse.wheel(0, Math.sign(dy) * step); await page.waitForTimeout(ms) }
      await page.waitForTimeout(300)
    },
    /** Wheel until a locator is fully inside the given box (the scroll container's visible part). */
    async wheelTo(locator, { top = 120, bottom = 820, max = 60, step = 120, capMs = 8000 } = {}) {
      // Stops when the target is in the band, when scrolling no longer moves it (the end of the page), or after capMs.
      const start = Date.now()
      let last = null
      for (let i = 0; i < max && Date.now() - start < capMs; i++) {
        const b = await locator.boundingBox({ timeout: 5000 }).catch(() => null)
        if (b && b.y >= top && b.y + b.height <= bottom) break
        if (b && last !== null && Math.abs(b.y - last) < 1) break
        last = b ? b.y : null
        await page.mouse.wheel(0, !b || b.y > bottom - b.height ? step : -step)
        await page.waitForTimeout(35)
      }
      await page.waitForTimeout(300)
    },
    setMouse(p) { mouse = p },
    async finish() {
      await page.waitForTimeout(2000) // hold the last frame
      f.hide()
      const video = page.video()
      await context.close()
      const tmp = await video.path()
      renameSync(tmp, `${raw}/${name}.webm`)
      const out = { film: name, segments: segments.map(([a, b]) => [Number(a.toFixed(2)), Number(b.toFixed(2))]),
        poster: f.poster?.at ?? null, writes, errors, slow: f.trace }
      writeFileSync(`${raw}/${name}.json`, JSON.stringify(out, null, 1))
      return out
    },
  }
  // A step that runs well past its intended time (the box was slow) has its middle cut out, as loading frames are:
  // the film keeps its start and end, never a sped-up copy. Only the outermost step cuts.
  const trace = []
  const intended = { moveTo: (a) => (a[2] ?? 550) / 1000, point: (a) => (a[1]?.ms ?? 550) / 1000,
    click: (a) => (a[1]?.ms ?? 550) / 1000 + 0.3, clickAt: (a) => (a[2] ?? 500) / 1000 + 0.3, wheel: () => 1.0, wheelTo: () => 1.5 }
  let depth = 0
  for (const k of ["goto", "until", "pause", "moveTo", "point", "click", "clickAt", "wheel", "wheelTo"]) {
    const fn = f[k]
    f[k] = async (...a) => {
      const s0 = now()
      depth += 1
      try { return await fn(...a) } finally {
        depth -= 1
        const d = now() - s0
        if (d > 2.5 && k !== "pause" && k !== "goto") trace.push(`${s0.toFixed(1)} ${k} ${d.toFixed(1)} s ${String(a[0]).slice(0, 80)}`)
        const want = intended[k]?.(a)
        if (depth === 0 && want !== undefined && d > want + 1.2 && open !== null && open < s0) {
          const keep = Math.min(0.5, want / 2)
          segments.push([open, s0 + keep]); open = now() - keep
        }
      }
    }
  }
  f.trace = trace
  return f
}

/** No progress text left on the page ("7 of 8 parts loaded", "Loading the review queue"). */
const settled = (page) => page.waitForFunction(
  () => !/\d+ of \d+ parts loaded|Loading the |Loading casework|Loading page \d|Loading transaction|Loading [^\n]*(…|\.\.\.)|Reading the theory…|Drawing the page|Working out /.test(document.body.innerText),
  null, { timeout: 90_000, polling: 250 }).catch(() => {})

const visible = (page, text, opts = {}) => page.getByText(text, opts).first().waitFor({ state: "visible", timeout: 90_000 })

/** Run a Together comparison off film and wait until its result and map have finished loading. */
async function together(page, other, from, to, done) {
  await visible(page, "Compare with")
  await page.locator("select").nth(1).selectOption({ label: other })
  const d = page.locator('input[type="date"]')
  await d.nth(0).fill(from)
  await d.nth(1).fill(to)
  await page.getByRole("button", { name: new RegExp(`^Compare ${from} to ${to}`) }).click()
  await visible(page, done)
  await page.waitForFunction(() => !/could not be loaded|Loading the map/.test(document.body.innerText), null, { timeout: 60_000 })
  await settled(page)
  await page.waitForTimeout(2500) // the base map paints
}

const FILMS = {
  // Section 1: a question to the assistant; its first lease citation opens the lease at the rent line.
  async opening(f) {
    const { page } = f
    await f.goto(`agent?thread=${T.rent}`, () => visible(page, /^The \$650 monthly payments into the Ruiz Auto/))
    await f.pause(1600)
    const answer = page.getByText(/^The \$650 monthly payments into the Ruiz Auto/).first()
    await f.point(answer, { dx: 0.35, dy: 0.5, ms: 650 })
    await f.pause(900)
    const cite = page.locator('button[data-citation-scheme="doc"]', { hasText: "document, p.1" }).first()
    await f.wheelTo(cite, { top: 330, bottom: 540 })
    await f.pause(1000)
    await f.click(cite)
    const dialog = page.getByRole("dialog").first()
    await f.until(async () => {
      await dialog.getByText("bay4-lease-2023-10-01.pdf").first().waitFor({ timeout: 60_000 })
      await page.waitForFunction(() => [...document.querySelectorAll('[role="dialog"] img, [role="dialog"] canvas')]
        .some((e) => (e.tagName === "IMG" ? e.complete && e.naturalWidth > 200 : e.width > 200)), null, { timeout: 60_000 })
    })
    await f.pause(900)
    // Point at the rent line: the page image is 902 px wide at 100 %, the line sits 206 px below its top.
    const pageImg = dialog.locator("img, canvas").first()
    const b = await pageImg.boundingBox()
    if (b) await f.moveTo(b.x + b.width * 0.1, b.y + b.width * 0.229, 700)
    f.markPoster()
    await f.pause(2400)
  },

  // Section 5: the review queue holding Kell's May statement, then the $9,800.00 deposit beside its printed line.
  async money(f) {
    const { page } = f
    await f.goto("financial", () => visible(page, "Check the 1 statement"))
    await f.pause(700)
    await f.click(page.getByText("Check the 1 statement").first())
    await f.until(() => visible(page, "kell-2024-05.pdf"))
    await f.pause(300)
    const reason = page.getByText("The balances do not add up").first()
    await f.point(reason, { ms: 600 })
    await f.wheel(270)
    await f.point(page.getByText(/pages may be missing/).first(), { dx: 0.3, ms: 650 })
    f.markPoster()
    await f.pause(1700)
    await f.goto(`financial?view=transactions&payment=${T.deposit}`, () => visible(page, "9,800.00 USD"))
    const dialog = page.getByRole("dialog").first()
    await f.pause(300)
    await f.point(dialog.getByText("9,800.00 USD").first(), { ms: 550 })
    await f.pause(1200)
    const show = dialog.getByText("Show highlighted value").first()
    await f.moveTo(720, 600, 400)
    await f.wheelTo(show, { top: 200, bottom: 700 })
    await f.click(show)
    await f.until(() => page.waitForTimeout(1200))
    // The highlighted row is drawn inside the scrollable page; bring it on screen and point at the printed "9   800.00".
    await page.evaluate(() => {
      const region = document.querySelector('[aria-label="Scrollable source page"]')
      const hl = [...region.querySelectorAll("div")].find((e) => getComputedStyle(e).position === "absolute" && e.getBoundingClientRect().width > 200)
      if (hl) hl.setAttribute("data-film", "highlight")
    })
    const hl = page.locator('[data-film="highlight"]')
    if (await hl.count()) {
      await f.moveTo(560, 300, 400) // over the dialog's text, so the wheel scrolls the dialog, not the page image
      await f.wheelTo(hl, { top: 380, bottom: 780 })
      // Then scroll the page image itself (the pointer over it) until the row sits in the middle of the screen.
      const region = await page.locator('[aria-label="Scrollable source page"]').boundingBox()
      if (region) await f.moveTo(region.x + region.width * 0.3, Math.min(region.y + region.height / 2, 780), 400)
      await f.wheelTo(hl, { top: 420, bottom: 700, step: 60 })
      await f.point(hl, { dx: 0.69, ms: 650 })
    }
    await f.pause(2200)
  },

  // Section 6: the hour grid for Kell's phone, then Kell's phone and the glovebox phone together.
  async phones(f) {
    const { page } = f
    await f.goto("phone-patterns", () => visible(page, "Pattern grid", { exact: true }))
    // The Day view it opens on has rows with 0 items; the film starts on Phone 2's grid instead.
    f.hide()
    await page.locator("select").first().selectOption({ label: "Phone 2" })
    await page.getByRole("button", { name: "Pattern grid", exact: true }).click()
    await visible(page, "Use counted")
    await settled(page)
    await page.waitForTimeout(400)
    f.show()
    await f.pause(900)
    await f.point(page.getByText("2024-05-31", { exact: true }).first(), { ms: 550 })
    f.markPoster()
    await f.pause(1800)
    await f.click(page.getByRole("button", { name: "Together", exact: true }))
    // Together first runs a default week against another phone, with a map still loading: that stretch is cut, and
    // the film resumes on the finished comparison (the button keeps the dates it ran).
    f.hide()
    await together(page, "Phone 3", "2024-05-23", "2024-06-07", /Episodes \(3\d\)/)
    f.show()
    await f.point(page.getByText(/pairs compared/).first(), { dx: 0.2, ms: 450 })
    await f.pause(1300)
    const ep = page.getByText(/^Episodes \(\d+\)/).first()
    await f.wheelTo(ep, { top: 300, bottom: 600 }) // the pointer is over the sentence, so the page scrolls, not the map
    await f.point(ep, { dx: 0.2, ms: 500 })
    await f.pause(2000)
  },

  // Section 4: Mateo and Okafor at the hardware store, graded weak with its reasons.
  async traps(f) {
    const { page } = f
    await f.goto("phone-analyses/two-phones", () => visible(page, "Together or apart (7)"))
    // The page opens on "In common (0)", an empty list: the film starts on "Together or apart" instead.
    f.hide()
    await page.getByText("Together or apart (7)").first().click()
    await visible(page, "Weak. Phone 1 and Phone 4")
    await settled(page)
    await page.waitForTimeout(400)
    f.show()
    await f.pause(1000)
    const card = page.getByText("Weak. Phone 1 and Phone 4").first()
    await f.click(card, { dx: 0.3 })
    await f.until(() => visible(page, /Only 5 decided quarter hours/))
    await f.wheelTo(page.getByText(/Only 5 decided quarter hours/).first(), { top: 150, bottom: 760 })
    await f.point(page.getByText(/^Weak: 5 decided quarter hours/).first(), { dx: 0.25, ms: 650 })
    f.markPoster()
    await f.pause(2200)
    await f.goto("phone-patterns", () => visible(page, "Together", { exact: true }))
    // The Day view it opens on (rows with 0 items) and Together's default week are cut; the film resumes on the result.
    f.hide()
    await page.getByRole("button", { name: "Together", exact: true }).click()
    await together(page, "Phone 4", "2024-05-18", "2024-05-18", /compatible \(tight\)/)
    f.show()
    await f.point(page.getByText(/pairs compared/).first(), { dx: 0.3, ms: 500 }) // over text, not the map
    await f.wheelTo(page.getByText(/compatible \(tight\)/).first(), { top: 300, bottom: 820 })
    await f.point(page.getByText(/compatible \(tight\)/).first(), { dx: 0.3, ms: 650 })
    await f.pause(2200)
  },

  // Section 7: the Timeline on 12-15 April, Mateo's phone that night, and Vint's payment on 15 April.
  async connect(f) {
    const { page } = f
    await f.goto("timeline", () => visible(page, "Custom", { exact: true }))
    await f.pause(900)
    await f.click(page.getByRole("button", { name: "Custom" }))
    const d = page.locator('input[type="date"]')
    await f.point(d.nth(0), { ms: 450 }); await d.nth(0).fill("2024-04-12")
    await f.point(d.nth(1), { ms: 450 }); await d.nth(1).fill("2024-04-15")
    await f.until(() => visible(page, "Theft at Brightwater Logistics"))
    await f.pause(1200)
    await f.click(page.getByRole("button", { name: "What the phones did" }))
    await f.until(() => page.locator('[title="Apr 13, 2024 · 9 entries"]').first().waitFor({ timeout: 60_000 }))
    await f.pause(900)
    await f.click(page.locator('[title="Apr 13, 2024 · 9 entries"]').first())
    await f.until(() => visible(page, "Call, 2 min 20 s, answered"))
    const call = page.getByText("Call, 2 min 20 s, answered").first()
    await f.moveTo(800, 600, 400)
    await f.wheelTo(page.getByText("I'm on Hobbet Mill past the reservoir sign, silver sedan, hazards on").first(), { top: 300, bottom: 820 })
    await f.point(call, { dx: 0.3, ms: 650 })
    f.markPoster()
    await f.pause(1600)
    await f.point(page.getByText("I'm on Hobbet Mill past the reservoir sign, silver sedan, hazards on").first(), { dx: 0.3, ms: 600 })
    await f.pause(1600)
    await f.click(page.getByRole("button", { name: "What the phones did" }))
    await f.until(() => visible(page, "Theft at Brightwater Logistics"))
    await f.pause(500)
    const vint = page.getByText("VINT H TOW INV 1187").first()
    await f.moveTo(900, 560, 450) // over the events list
    await f.wheelTo(vint, { top: 250, bottom: 820, max: 120, step: 200, capMs: 20000 })
    await f.point(vint, { dx: 0.4, ms: 650 })
    await f.pause(2200)
  },

  // Section 8: the Map over Baltimore; an area drawn around the warehouse lists the phones seen inside it.
  async "time-and-place"(f) {
    const { page } = f
    const mapReady = async () => {
      await page.locator("canvas").first().waitFor({ timeout: 90_000 })
      await page.waitForFunction(() => {
        const el = document.querySelector(".maplibregl-map") || document.querySelector("canvas")?.parentElement
        const key = el && Object.keys(el).find((k) => k.startsWith("__reactFiber"))
        for (let f = key ? el[key] : null, i = 0; f && i < 60; i++, f = f.return) {
          for (let s = f.memoizedState, j = 0; s && j < 30; s = s.next, j++) {
            const v = s.memoizedState
            if (v && typeof v === "object" && v.current && typeof v.current.getCenter === "function") { window.__filmMap = v.current; break }
          }
          if (window.__filmMap) break
        }
        const m = window.__filmMap
        return !!m && m.loaded() && m.areTilesLoaded()
      }, null, { timeout: 120_000, polling: 500 })
      await page.waitForTimeout(1500)
    }
    const at = () => page.evaluate((w) => {
      const m = window.__filmMap, r = m.getCanvas().getBoundingClientRect(), p = m.project(w)
      return { x: r.left + p.x, y: r.top + p.y, cx: r.left + r.width / 2, cy: r.top + r.height / 2 }
    }, T.warehouse)
    // Opened as "Show on Map" does (?phone_point=lon,lat: the phone layer centred on the warehouse at zoom 15), then
    // zoomed out around it so Baltimore shows; the map zooms around the pointer, so the warehouse stays in the middle.
    await f.goto(`map?phone_point=${T.warehouse.join(",")}`, mapReady)
    await f.pause(900)
    let p = await at()
    await f.moveTo(p.x, p.y, 600)
    for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, 240); await page.waitForTimeout(450) }
    await f.until(() => page.waitForFunction(() => window.__filmMap.areTilesLoaded(), null, { timeout: 60_000 }))
    await f.pause(1000)
    await f.click(page.getByRole("button", { name: /Areas/ }).first())
    await f.pause(700)
    await f.click(page.getByRole("button", { name: /Draw area/ }).first())
    p = await at()
    const r = 70
    await f.moveTo(p.x - r, p.y - r, 600)
    await page.mouse.down()
    await f.moveTo(p.x + r, p.y + r, 1100)
    await page.mouse.up()
    await f.pause(600)
    await f.click(page.getByRole("button", { name: "Apply" }).first())
    await f.until(() => page.locator('[aria-label="Phones seen in this area"] [role="status"]').first().waitFor({ timeout: 60_000 }))
    await f.pause(500)
    await f.point(page.locator('[aria-label="Phones seen in this area"] [role="status"]').first(), { dx: 0.3, ms: 650 })
    f.markPoster()
    await f.pause(2600)
  },

  // Section 9: the defence theory, its reading as a timeline, and what "What breaks this theory" offers.
  async theory(f) {
    const { page } = f
    await f.goto("workspace?view=casework", () => visible(page, "T2 Defence theory"))
    await f.pause(1100)
    await f.click(page.getByText("T2 Defence theory").first(), { dx: 0.3 })
    await f.until(() => visible(page, "Linked material"))
    await f.pause(1500)
    const ra = page.getByText("Reading & analysis", { exact: true }).first()
    await f.moveTo(980, 600, 400)
    await f.wheelTo(ra, { top: 300, bottom: 800 })
    await f.click(ra)
    // The section opens with "Reading the theory..." while it loads: always cut, however short.
    await f.until(async () => {
      await page.waitForTimeout(150)
      await page.waitForFunction(() => !/Reading the theory/.test(document.body.innerText), null, { timeout: 60_000 })
      await settled(page)
    }, { min: 0 })
    await f.pause(800)
    const tl = page.getByRole("button", { name: "As a timeline" }).first()
    await f.wheelTo(tl, { top: 200, bottom: 600 })
    await f.click(tl)
    await f.until(() => page.waitForTimeout(1500))
    f.markPoster()
    await f.pause(2000)
    const wb = page.getByRole("heading", { name: "What breaks this theory" }).first()
    await f.wheelTo(wb, { top: 140, bottom: 420, max: 120 })
    await f.point(wb, { ms: 600 })
    await f.pause(1500)
    const look = page.getByRole("button", { name: /Look for other explanations/ }).first()
    if (await look.isVisible().catch(() => false)) await f.point(look, { ms: 600 })
    await f.pause(2400)
  },

  // Section 10: the storage-unit question, its cited answer, the rental agreement, and what the run did not read.
  async assistant(f) {
    const { page } = f
    await f.goto(`agent?thread=${T.unit212}`, () => visible(page, "Storage unit 212 at Stowell Self Storage was rented"))
    await f.pause(1600)
    const line = page.getByText(/debit card ending 4471, cardholder TRAVIS KELL/).first()
    await f.wheelTo(line, { top: 300, bottom: 560 })
    await f.point(line, { dx: 0.3, ms: 650 })
    await f.pause(1200)
    const cite = line.locator('button[data-citation-scheme="doc"]').first()
    await f.click(cite)
    const dialog = page.getByRole("dialog").first()
    await f.until(async () => {
      await dialog.getByText("stowell-rental-agreement-unit-212.pdf").first().waitFor({ timeout: 60_000 })
      await page.waitForFunction(() => [...document.querySelectorAll('[role="dialog"] img, [role="dialog"] canvas')]
        .some((e) => (e.tagName === "IMG" ? e.complete && e.naturalWidth > 200 : e.width > 200)), null, { timeout: 60_000 })
    })
    await f.pause(800)
    const img = dialog.locator("img, canvas").first()
    const b = await img.boundingBox()
    if (b) await f.moveTo(b.x + b.width * 0.37, b.y + b.width * 0.207, 700) // "debit card ending 4471, cardholder TRAVIS KELL"
    f.markPoster()
    await f.pause(2400)
    await f.click(dialog.getByRole("button", { name: "Close" }).first())
    await f.pause(700)
    const rr = page.getByRole("button", { name: "Run record" }).first()
    await f.wheelTo(rr, { top: 300, bottom: 700 })
    await f.click(rr)
    await f.until(() => visible(page, "What was not examined (PDF)"))
    const ne = page.getByText("What was not examined (PDF)").first()
    await f.wheelTo(ne, { top: 300, bottom: 640 })
    await f.point(page.getByText("Tool calls", { exact: true }).first(), { ms: 600 })
    await f.pause(1300)
    await f.point(ne, { ms: 600 })
    await f.pause(2200)
  },

  // Section 9 (lx-sitecopy): the defence theory's linked material, each item marked Supports, Context or Contradicts,
  // then the for-and-against comparison. Points only: a mark is never clicked (a click there would change it).
  async "theory-marks"(f) {
    const { page } = f
    await f.goto("workspace?view=casework", () => visible(page, "T2 Defence theory"))
    await f.pause(600)
    await f.click(page.getByText("T2 Defence theory").first(), { dx: 0.3 })
    // The sheet opens on "Loading casework": the film cuts at the click and resumes on the loaded sheet.
    f.hide()
    await visible(page, "Linked material")
    await settled(page)
    await page.waitForTimeout(400)
    f.show()
    await f.pause(800)
    const sheet = page.getByRole("dialog").first()
    await f.point(sheet.getByText("Unit 212 paid by Kell's card").first(), { dx: 0.3, ms: 600 })
    await f.pause(400)
    await f.point(sheet.getByText("Supports", { exact: true }).nth(3), { ms: 550 })
    await f.pause(900)
    await f.point(sheet.getByText("Context", { exact: true }).first(), { ms: 600 })
    await f.pause(700)
    const against = sheet.getByText("Kell says the phone was Mateo's").first()
    await f.point(against, { dx: 0.3, ms: 550 })
    await f.pause(500)
    await f.point(sheet.getByText("Contradicts", { exact: true }).first(), { ms: 550 })
    f.markPoster()
    await f.pause(1000)
    const cmp = sheet.getByText(/^Compare what supports and contradicts it/).first()
    await f.moveTo(980, 600, 400)
    await f.wheelTo(cmp, { top: 200, bottom: 420 })
    await f.click(cmp, { dx: 0.3 })
    await f.until(() => sheet.locator('[data-testid="compare-contradicts"]').first().waitFor({ state: "visible", timeout: 30_000 }))
    await f.wheelTo(sheet.locator('[data-testid="compare-contradicts"]').first(), { top: 200, bottom: 820 })
    await f.point(sheet.locator('[data-testid="compare-supports"]').first(), { dx: 0.3, dy: 0.4, ms: 600 })
    await f.pause(1200)
    await f.point(sheet.locator('[data-testid="compare-contradicts"]').first(), { dx: 0.3, dy: 0.3, ms: 600 })
    await f.pause(1500)
  },

  // Section 10 (lx-sitecopy): the storage-unit answer, the source check that closes it, and a citation it checked.
  async "assistant-check"(f) {
    const { page } = f
    await f.goto(`agent?thread=${T.unit212}`, () => visible(page, "Storage unit 212 at Stowell Self Storage was rented"))
    await f.pause(1400)
    await f.point(page.getByText(/^Storage unit 212 at Stowell Self Storage was rented/).first(), { dx: 0.3, ms: 600 })
    await f.pause(1000)
    const check = page.getByText(/^Source check: \d+ of \d+ citations support their sentence/).first()
    await f.moveTo(800, 560, 400)
    await f.wheelTo(check, { top: 380, bottom: 700 })
    await f.point(check, { dx: 0.2, ms: 650 })
    f.markPoster()
    await f.pause(2600)
    const line = page.getByText(/debit card ending 4471, cardholder TRAVIS KELL/).first()
    await f.wheelTo(line, { top: 260, bottom: 560 })
    await f.point(line, { dx: 0.3, ms: 600 })
    await f.pause(900)
    await f.click(line.locator('button[data-citation-scheme="doc"]').first())
    const dialog = page.getByRole("dialog").first()
    // The viewer opens on "Loading page 1...": the film cuts at the click and resumes on the drawn page.
    f.hide()
    await (async () => {
      await dialog.getByText("stowell-rental-agreement-unit-212.pdf").first().waitFor({ timeout: 60_000 })
      await page.waitForFunction(() => [...document.querySelectorAll('[role="dialog"] img, [role="dialog"] canvas')]
        .some((e) => (e.tagName === "IMG" ? e.complete && e.naturalWidth > 200 : e.width > 200)), null, { timeout: 60_000 })
    })()
    // The viewer draws the page, then draws it again once its page count arrives ("Page 1 of 1"): wait out both.
    await settled(page)
    await page.waitForTimeout(1500)
    await settled(page)
    await page.waitForTimeout(400)
    f.show()
    await f.pause(500)
    const img = dialog.locator("img, canvas").first()
    const b = await img.boundingBox()
    if (b) await f.moveTo(b.x + b.width * 0.37, b.y + b.width * 0.207, 700) // "debit card ending 4471, cardholder TRAVIS KELL"
    await f.pause(2400)
  },

  // Section 11: Travis Kell in the graph, a fact drawn from the lease, and the lease page it came from.
  async trust(f) {
    const { page } = f
    const graphReady = () => page.waitForFunction(() => {
      const c = document.querySelector("canvas"); return !!c && c.width > 300
    }, null, { timeout: 90_000 }).then(() => page.waitForTimeout(2500))
    await f.goto("graph", graphReady)
    await f.pause(1000)
    const filter = page.getByPlaceholder("Filter graph...")
    await f.click(filter)
    await filter.pressSequentially("Travis Kell", { delay: 70 })
    await filter.press("Enter")
    await f.until(() => page.waitForTimeout(3500))
    const node = () => page.evaluate(() => {
      const canvas = document.querySelector("canvas"); let fg = null, gd = null
      for (let el = canvas, k = 0; el && k < 8 && !(fg && gd); k++, el = el.parentElement) {
        const key = Object.keys(el).find((x) => x.startsWith("__reactFiber"))
        for (let f = key ? el[key] : null, i = 0; f && i < 80; i++, f = f.return) {
          if (!gd && f.memoizedProps?.graphData?.nodes) gd = f.memoizedProps.graphData
          for (let s = f.memoizedState, j = 0; s && j < 40 && !fg; s = s.next, j++) {
            const v = s.memoizedState; const c = v && typeof v === "object" ? (v.current ?? v) : null
            if (c && typeof c.graph2ScreenCoords === "function") fg = c
          }
          if (fg && gd) break
        }
      }
      const n = gd?.nodes.find((x) => x.label === "Travis Kell" && x.type === "person")
      if (!fg || !n) return null
      const p = fg.graph2ScreenCoords(n.x, n.y), r = canvas.getBoundingClientRect()
      return { x: r.left + p.x, y: r.top + p.y }
    })
    let p = await node()
    if (!p) throw new Error("Travis Kell is not in the filtered graph")
    await f.moveTo(p.x, p.y, 650)
    for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, -200); await page.waitForTimeout(250) }
    await f.pause(700)
    p = await node()
    await f.clickAt(p.x, p.y, 300)
    await f.until(() => visible(page, "SOURCE-GROUNDED FACTS"))
    await f.pause(1300)
    const facts = page.getByText("SOURCE-GROUNDED FACTS").first()
    const pb = await facts.boundingBox()
    await f.moveTo(pb.x + 150, 600, 500)
    await f.wheelTo(facts, { top: 470, bottom: 520, max: 80 })
    await f.pause(900)
    await f.click(page.getByText(/^Show \d+ more$/).first())
    const fact = page.getByText("Travis Kell is the tenant in the lease agreement.", { exact: true }).first()
    await f.wheelTo(fact, { top: 420, bottom: 700, max: 80 })
    await f.point(fact, { dx: 0.4, ms: 650 })
    f.markPoster()
    await f.pause(1800)
    await f.click(fact.locator("xpath=following-sibling::button[1]"))
    const dialog = page.getByRole("dialog").first()
    await f.until(async () => {
      await dialog.getByText("bay4-lease-2023-10-01.pdf").first().waitFor({ timeout: 60_000 })
      await page.waitForFunction(() => [...document.querySelectorAll('[role="dialog"] img, [role="dialog"] canvas')]
        .some((e) => (e.tagName === "IMG" ? e.complete && e.naturalWidth > 200 : e.width > 200)), null, { timeout: 60_000 })
    })
    await f.pause(800)
    const img = dialog.locator("img, canvas").first()
    const b = await img.boundingBox()
    if (b) await f.moveTo(b.x + b.width * 0.42, b.y + b.width * 0.137, 700)
    await f.pause(2400)
  },
}

const login = readLogin()
const browser = await chromium.launch()
const results = []
try {
  // Sign in once; every film's context starts from this session.
  const { context } = await signIn(browser, login)
  const state = await context.storageState()
  await context.close()
  for (const [name, run] of Object.entries(FILMS)) {
    if (only && !only.has(name)) continue
    const started = Date.now()
    const f = await makeFilm(browser, state, name)
    f.base = Promise.resolve(login.url)
    let failed = null
    try {
      await run(f)
    } catch (e) {
      failed = String(e?.message ?? e).split("\n")[0].slice(0, 240)
      await f.page.screenshot({ path: `${raw}/${name}-failed.png` }).catch(() => {})
    }
    const out = await f.finish()
    if (out.writes.length) failed = failed || `requests that may write: ${out.writes.join(", ")}`
    const kept = out.segments.reduce((s, [a, b]) => s + (b - a), 0)
    results.push({ ...out, failed, kept_s: Number(kept.toFixed(1)), wall_s: Math.round((Date.now() - started) / 1000) })
    console.log(`${name.padEnd(16)} ${failed ? `FAILED ${failed}` : "ok"}  kept ${kept.toFixed(1)} s  ${out.errors.length} errors`)
  }
} finally {
  await browser.close()
}
const out = arg("out")
if (out) writeFileSync(out, JSON.stringify(results, null, 1))
