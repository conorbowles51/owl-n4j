/**
 * The decisions read, and the contract it depends on.
 *
 * The same two kinds of test as `api.ledger.test.ts` and `api.runs.test.ts`,
 * and for the same reason: the log is written by Python and read by
 * TypeScript, and nothing between the two will notice if one side moves.
 *
 * Two differences from the other two reads are what most of the tests below
 * exist to hold in place.
 *
 * **This read is bounded and the other two are not.** So a default sent from
 * this side, or a bound declared on it, does not merely duplicate the backend
 * -- it changes which decisions a case appears to have. The endpoint refuses a
 * limit below 1 and caps one above its own maximum, and those two rules are
 * deliberately not the same rule. Anything on this side that tried to express
 * them would express only one.
 *
 * **A truncated history that does not say it was truncated is worse than no
 * history.** `total` and `truncated` are as much part of the answer as the
 * records are, so the shape tests below hold the whole envelope and not just
 * the rows inside it.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  ADJUDICATION_DECISIONS,
  ADJUDICATION_SUBJECTS,
  DECISION_FIELDS,
  financialAPI,
  type DecisionRecord,
} from "./api"

const here = dirname(fileURLToPath(import.meta.url))
const backend = (...parts: string[]) =>
  resolve(here, "../../../../backend", ...parts)

function read(path: string): string {
  return readFileSync(path, "utf8")
}

/**
 * From a declaration at column zero to the next one.
 *
 * See `api.ledger.test.ts`: scoped so an identical member of a different enum
 * cannot pass. It matters more here than there, because `decision_log.py`
 * declares two classes that each have an `as_dict`, and an unscoped search
 * would read the first one twice.
 */
function pythonBlock(source: string, header: string): string {
  const opens = source.indexOf(header)
  expect(opens, `${header} is no longer declared`).toBeGreaterThan(-1)
  const rest = source.slice(opens + header.length)
  const next = rest.search(/\n(?=\S)/)
  return next === -1 ? rest : rest.slice(0, next)
}

function enumMembers(source: string, header: string): string[] {
  const block = pythonBlock(source, header)
  return [...block.matchAll(/^ {4}(\w+) = "([^"]*)"/gm)].map((m) => m[2])
}

/** The keys one class's `as_dict` puts on the wire, in the order it emits them. */
function emittedKeys(classBody: string): string[] {
  const opens = classBody.indexOf("def as_dict(self)")
  expect(opens, "as_dict is no longer declared here").toBeGreaterThan(-1)
  return [...classBody.slice(opens).matchAll(/"([a-z_0-9]+)":/g)].map((m) => m[1])
}

/** One route's declaration and body, from its decorator to the next one. */
function routeBody(source: string, decorator: string): string {
  const opens = source.indexOf(decorator)
  expect(opens, `${decorator} is no longer declared`).toBeGreaterThan(-1)
  const next = source.indexOf("\n@router.", opens + decorator.length)
  return next === -1 ? source.slice(opens) : source.slice(opens, next)
}

/* ------------------------------------------------------------------ *
 * What this file sends
 * ------------------------------------------------------------------ */

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function requestedUrl(): string {
  const call = vi.mocked(globalThis.fetch).mock.calls[0]
  return String(call[0])
}

const emptyPage = {
  case_id: "case-1",
  decisions: [],
  total: 0,
  limit: 100,
  offset: 0,
  truncated: false,
}

describe("financialAPI.getCaseDecisions", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(emptyPage))
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("asks the decisions endpoint, not the ledger or runs one", async () => {
    await financialAPI.getCaseDecisions({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.pathname).toBe("/api/financial/decisions")
  })

  it("sends nothing but the case when nothing else was asked for", async () => {
    // No filters means no filters. A subject_type or decision leaking in here
    // would narrow a history while looking like the whole of it, which on an
    // audit trail is the one failure that cannot be seen from the screen.
    await financialAPI.getCaseDecisions({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({ case_id: "case-1" })
  })

  it("sends no page size of its own", async () => {
    // The endpoint has a default and a cap, and they are enforced by the
    // service that knows they are different rules: below 1 is refused, above
    // the cap is capped and answered. A default sent from here would be a
    // second copy of a bound, and a second copy is what drifts.
    await financialAPI.getCaseDecisions({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.has("limit")).toBe(false)
    expect(url.searchParams.has("offset")).toBe(false)
  })

  it("sends every filter it was given, under the names the endpoint reads", async () => {
    await financialAPI.getCaseDecisions({
      caseId: "case-1",
      subjectType: "transaction",
      subjectId: "row-9",
      decision: "quarantine_row",
      limit: 25,
      offset: 50,
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      case_id: "case-1",
      subject_type: "transaction",
      subject_id: "row-9",
      decision: "quarantine_row",
      limit: "25",
      offset: "50",
    })
  })

  it("sends a subject id without a subject type", async () => {
    // The endpoint allows the pair to be given apart, and the records name
    // their own subject type. Requiring both here would be a rule this side
    // invented.
    await financialAPI.getCaseDecisions({ caseId: "case-1", subjectId: "row-9" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      case_id: "case-1",
      subject_id: "row-9",
    })
  })

  it("sends a limit of zero rather than dropping it", async () => {
    // `if (params.limit)` would swallow 0 and return a full page to a caller
    // who asked for none. The backend refuses 0 with a 400 carrying its own
    // words, and that refusal is the answer that caller should get.
    await financialAPI.getCaseDecisions({ caseId: "case-1", limit: 0 })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("limit")).toBe("0")
  })

  it("sends an offset of zero rather than dropping it", async () => {
    // Harmless in itself -- zero is the endpoint's own default -- but the
    // guard is the same guard, and a truthiness test that swallows one of the
    // two would swallow the other.
    await financialAPI.getCaseDecisions({ caseId: "case-1", offset: 0 })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("offset")).toBe("0")
  })

  it("sends a limit above the cap rather than refusing it here", async () => {
    // The endpoint caps and answers. A bound on this side would turn a
    // request the backend is willing to serve into one it never sees.
    await financialAPI.getCaseDecisions({ caseId: "case-1", limit: 100000 })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("limit")).toBe("100000")
  })

  it("escapes values rather than pasting them into the query string", async () => {
    await financialAPI.getCaseDecisions({ caseId: "a&decision=release_row" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("case_id")).toBe("a&decision=release_row")
    expect(url.searchParams.has("decision")).toBe(false)
  })

  it("hands back the page whole, total and truncation included", async () => {
    // Not the records alone. A caller that unwrapped `decisions` here would
    // leave every screen unable to say the history it is showing stops short.
    const page = {
      case_id: "case-1",
      decisions: [{ id: "d-1" }],
      total: 412,
      limit: 100,
      offset: 0,
      truncated: true,
    }
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(page))

    const result = await financialAPI.getCaseDecisions({ caseId: "case-1" })
    expect(result).toEqual(page)
  })
})

/* ------------------------------------------------------------------ *
 * What the backend actually offers
 * ------------------------------------------------------------------ */

describe("the decisions endpoint contract", () => {
  const router = () => read(backend("routers/financial_ledger.py"))

  it("is still mounted where this file asks for it", () => {
    const source = router()
    expect(source).toMatch(/prefix\s*=\s*"\/api\/financial"/)
    expect(source).toMatch(/@router\.get\("\/decisions"\)/)
  })

  it("is still on the router that resolves to a view permission", () => {
    // It is here rather than on the adjudication router, which puts every
    // route behind the write bar on purpose. If this router ever stopped
    // resolving to `view`, reading a case's history would start demanding the
    // permission to change it.
    const source = router()
    expect(source).toMatch(/return \("case", "view"\)/)
    expect(routeBody(source, '@router.get("/decisions")')).not.toMatch(
      /case_access_dependency/
    )
  })

  it("still reads every parameter this file sends", () => {
    const body = routeBody(router(), '@router.get("/decisions")')
    for (const param of [
      "case_id",
      "subject_type",
      "subject_id",
      "decision",
      "limit",
      "offset",
    ]) {
      expect(
        body,
        `${param} is no longer a parameter of GET /decisions`
      ).toMatch(new RegExp(`^\\s{4}${param}:`, "m"))
    }
  })

  it("still leaves the page bounds to the service rather than to Query", () => {
    // This is what makes "send 0" and "send a large limit" the right
    // behaviour on this side. A `ge=` or `le=` added to the route would turn
    // both into a 422 raised before the service ever saw them, and the
    // service is the only place that knows a low limit is refused while a
    // high one is answered.
    const body = routeBody(router(), '@router.get("/decisions")')
    const limitOpens = body.indexOf("limit: int = Query(")
    const offsetOpens = body.indexOf("offset: int = Query(")
    expect(limitOpens, "the limit parameter is no longer declared").toBeGreaterThan(-1)
    expect(offsetOpens, "the offset parameter is no longer declared").toBeGreaterThan(
      limitOpens
    )

    const limitParam = body.slice(limitOpens, offsetOpens)
    expect(limitParam).not.toMatch(/\bge\s*=/)
    expect(limitParam).not.toMatch(/\ble\s*=/)
  })

  it("still refuses an unknown member instead of filtering on nothing", () => {
    // A raw string reaching the service would match no row and the case would
    // look empty. The route turns it into a 400 that names the valid values.
    const source = router()
    const body = routeBody(source, '@router.get("/decisions")')
    expect(body).toMatch(
      /_parsed_member\(subject_type, AdjudicationSubject, "subject_type"\)/
    )
    expect(body).toMatch(/_parsed_member\(decision, AdjudicationDecision, "decision"\)/)
    expect(source).toMatch(/status_code=400/)
  })

  it("still answers with the whole page rather than a rebuilt one", () => {
    const body = routeBody(router(), '@router.get("/decisions")')
    expect(body).toMatch(/return page\.as_dict\(\)/)
  })
})

describe("the decision record shape", () => {
  const log = () => read(backend("services/financial/decision_log.py"))

  it("declares exactly the fields the backend emits", () => {
    const body = pythonBlock(log(), "class DecisionRecord:")
    const emitted = emittedKeys(body)

    expect(emitted.length).toBeGreaterThan(0)
    expect(new Set(emitted)).toEqual(new Set(DECISION_FIELDS))
  })

  it("lists every field the interface declares", () => {
    // Typed `keyof DecisionRecord`, so the list cannot name a field the
    // interface does not have. This closes the other direction at compile
    // time.
    const everyDeclaredFieldIsListed: [
      Exclude<keyof DecisionRecord, (typeof DECISION_FIELDS)[number]>,
    ] extends [never]
      ? true
      : false = true

    expect(everyDeclaredFieldIsListed).toBe(true)
  })

  it("still says which decisions a machine took", () => {
    // Derived from the actor's address rather than stored, and surfaced by
    // the backend rather than left to readers. A reader that computed it
    // wrongly would show software reclassifying a document as though an
    // analyst had, which is the most misleading thing this log could say.
    const body = pythonBlock(log(), "class DecisionRecord:")
    expect(emittedKeys(body)).toContain("by_machine")
    expect(log()).toMatch(/by_machine=actor_email\.strip\(\)\.lower\(\)/)
  })
})

describe("the decisions page envelope", () => {
  const log = () => read(backend("services/financial/decision_log.py"))

  it("still carries the total and the truncation flag beside the records", () => {
    // `DecisionsResponse` on this side declares both as required. If either
    // stopped being emitted, a screen built on it would show a page with no
    // way of saying what it was not showing.
    const body = pythonBlock(log(), "class DecisionPage:")
    expect(emittedKeys(body)).toEqual([
      "case_id",
      "decisions",
      "total",
      "limit",
      "offset",
      "truncated",
    ])
  })

  it("still reports the limit that was applied, not the one that was asked for", () => {
    // A limit above the cap comes back capped. Reading the page size from the
    // response rather than from the request is only correct because of this.
    expect(log()).toMatch(/return min\(limit, MAX_DECISION_LIMIT\)/)
  })

  it("still counts the total over the same filters as the page", () => {
    // A filtered page beside an unfiltered count would state a number that
    // answers no question the caller asked.
    expect(log()).toMatch(
      /select\(func\.count\(\)\)\.select_from\(AdjudicationEvent\)\.where\(\*filters\)/
    )
  })

  it("still orders newest first, with a tiebreak that makes the order total", () => {
    // Ordering is the backend's job and must not be redone on this side. The
    // three columns after `created_at` are what stop a row appearing on two
    // pages when several decisions share a timestamp.
    expect(log()).toMatch(
      /AdjudicationEvent\.created_at\.desc\(\),\s*\n\s*AdjudicationEvent\.subject_type,\s*\n\s*AdjudicationEvent\.subject_id,\s*\n\s*AdjudicationEvent\.subject_sequence\.desc\(\),/
    )
  })
})

describe("the adjudication vocabularies", () => {
  const enums = () => read(backend("postgres/models/enums.py"))

  it("still has the subjects this build knows", () => {
    expect(enumMembers(enums(), "class AdjudicationSubject(str, Enum):")).toEqual([
      ...ADJUDICATION_SUBJECTS,
    ])
  })

  it("still has the decisions this build knows, in the order that pairs them", () => {
    // Order is part of the contract here, not presentation. The vocabulary
    // groups each disposition with its reversal, and a screen that offers
    // these as filters should keep the pairs together.
    expect(enumMembers(enums(), "class AdjudicationDecision(str, Enum):")).toEqual([
      ...ADJUDICATION_DECISIONS,
    ])
  })
})
