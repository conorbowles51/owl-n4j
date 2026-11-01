// Live journey runner helpers (07 section 10.1 [S]). Runs in a real browser against the http address, signed in
// once with the jobs login, on synthetic cases only. Records counts, timings and failures as selector plus count;
// never page text, never screenshots of a real case. The password is read here and never printed.
import { readFileSync } from "node:fs"

export const CASES = {
  phonesOnly: "4aa79795-1076-4c75-985f-784936abb71f",
  training: "d9945277-6c80-4a39-82c7-93a95d420384",
  verification: "cded78d0-e659-44cc-940d-d8f8c8012760",
}
/** Writes and screenshots happen only in these cases (CB-INDEX rule 6). */
export const SYNTHETIC = new Set(Object.values(CASES))
/** Real phone reports load only into these restricted cases, each with its owner as the only member (CB-INDEX P3);
 * never into the verification case or any financial case. */
export const PHONE_REFERENCE_CASES = {
  phoneRef1: "88e01b57-d472-452a-b103-b694292ed012",
  phoneRef2: "7006c0ab-9c93-473a-900a-76d06d9d0603",
  phoneRef3: "574a9752-7d19-4f42-8f98-2112615f4a48",
}

export function readLogin(path = "/root/.config/loupe-jobs/login") {
  const fields = Object.fromEntries(
    readFileSync(path, "utf8").split("\n").filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()])
  )
  return { url: fields.url, email: fields.email, password: fields.password }
}

export class StepFailed extends Error {
  constructor(step, detail) {
    super(`${step}: ${detail}`)
    this.step = step
    this.detail = detail
  }
}

/** A journey's context: timed steps, action counting and the case guard. */
export function context(page, base, journey) {
  const steps = []
  let actions = 0
  const t0 = Date.now()
  const ctx = {
    base,
    cases: CASES,
    page,
    async open(caseId, path = "") {
      if (!SYNTHETIC.has(caseId)) throw new StepFailed("open", "refused: not a synthetic case")
      await page.goto(`${base}/cases/${caseId}${path}`, { waitUntil: "domcontentloaded" })
      const secure = await page.evaluate(() => window.isSecureContext)
      if (secure !== false) throw new StepFailed("open", "isSecureContext was not false (the test must run over plain http)")
    },
    /** One timed step: fn must resolve; a timeout or thrown error fails the journey at this step. */
    async step(name, fn, { limitMs } = {}) {
      const s = Date.now()
      try {
        await fn()
      } catch (e) {
        throw e instanceof StepFailed ? e : new StepFailed(name, String(e?.message ?? e).split("\n")[0].slice(0, 200))
      }
      const ms = Date.now() - s
      steps.push({ name, ms })
      if (limitMs && ms > limitMs) throw new StepFailed(name, `took ${ms} ms, limit ${limitMs} ms`)
    },
    async click(locator) {
      actions += 1
      await locator.click()
    },
    async press(key) {
      actions += 1
      await page.keyboard.press(key)
    },
    async see(locator, timeout = 5000) {
      await locator.first().waitFor({ state: "visible", timeout })
    },
    /** The count in a count sentence, e.g. "2,140 messages" -> 2140. */
    async countIn(locator, noun) {
      const text = await locator.first().innerText()
      const m = text.replace(/,/g, "").match(new RegExp(`(\\d+) ${noun}`))
      if (!m) throw new StepFailed("count", `no "<n> ${noun}" in the count sentence`)
      return Number(m[1])
    },
    async api(path) {
      return page.evaluate(async (p) => {
        const r = await fetch(p, { credentials: "include", headers: { Authorization: `Bearer ${localStorage.getItem("authToken") ?? ""}` } })
        return { status: r.status, body: r.ok ? await r.json() : null }
      }, path)
    },
    atMost(n, what = "actions") {
      if (actions > n) throw new StepFailed("actions", `${actions} ${what}, at most ${n}`)
    },
    result() {
      return { id: journey.id, owner: journey.owner, steps, actions, ms: Date.now() - t0 }
    },
  }
  return ctx
}

export async function signIn(browser, login) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  await page.goto(`${login.url}/login`, { waitUntil: "domcontentloaded" })
  await page.getByPlaceholder("Enter your username").fill(login.email)
  await page.getByPlaceholder("Enter your password").fill(login.password)
  await page.getByRole("button", { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 })
  return { context, page }
}
