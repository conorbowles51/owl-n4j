/**
 * Changing a row's standing, and the contract that write depends on.
 *
 * Two kinds of test, the same two as `api.ledger.test.ts`.
 *
 * The first kind checks what this file sends. These are the only two calls in
 * the financial feature that take a row out of the case's totals or put it
 * back, and both carry a written justification that is recorded verbatim
 * against a named person. A request that lands on the wrong path, names the
 * wrong case, or drops the justification into a query string the endpoint does
 * not read, fails in a way nobody sees until the log is asked to account for a
 * total and cannot.
 *
 * The second kind reads the backend source and requires the two languages to
 * still agree. The failure modes are the ledger read's, sharpened by the fact
 * that this endpoint writes: FastAPI accepts and ignores a renamed query
 * parameter, a new outcome arrives as a string this build has no name for, and
 * a field dropped from the response simply never appears. The one that matters
 * most is `rescues_period`. It is deliberately never written to the adjudication
 * log, so this response is the only place it is ever said; if the shape moves
 * and this build stops reading it, the fact is not degraded, it is gone.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  QUARANTINE_REASONS,
  ROW_ADJUDICATION_FIELDS,
  ROW_ADJUDICATION_OUTCOMES,
  financialAPI,
  type RowAdjudication,
} from "./api"

const here = dirname(fileURLToPath(import.meta.url))
const backend = (...parts: string[]) =>
  resolve(here, "../../../../backend", ...parts)

function read(path: string): string {
  return readFileSync(path, "utf8")
}

/**
 * The body of a Python block, from its header to the next line that starts in
 * column one. Scoping matters here for the same reason it does in the ledger
 * test: `reason` and `case_id` appear on both routes in this router and on
 * several routes elsewhere, so a whole-file search proves nothing about the
 * route actually being called.
 */
function pythonBlock(source: string, header: string): string {
  const opens = source.indexOf(header)
  expect(opens, `${header} is no longer declared`).toBeGreaterThan(-1)
  const next = source.slice(opens + header.length).search(/\n(?=\S)/)
  return next === -1
    ? source.slice(opens)
    : source.slice(opens, opens + header.length + next)
}

function enumMembers(source: string, header: string): string[] {
  const block = pythonBlock(source, header)
  return [...block.matchAll(/^ {4}(\w+) = "([^"]*)"/gm)].map((m) => m[2])
}

/* ------------------------------------------------------------------ *
 * What this file sends
 * ------------------------------------------------------------------ */

/**
 * A stub that builds a fresh response per call.
 *
 * Not `mockResolvedValue(new Response(...))`. That hands the same object to
 * every call, and a `Response` body can only be read once, so the second call
 * in a test dies with "Body is unusable" -- which reads exactly like the code
 * under test having failed. Several tests here make two calls, because the two
 * routes are only meaningfully different when compared.
 */
function answers(body: unknown): void {
  vi.mocked(globalThis.fetch).mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
  )
}

const ACCEPTED: RowAdjudication = {
  transaction_id: "txn-1",
  outcome: "quarantined",
  applied: true,
  reason: null,
  ledger_status: "quarantined",
  quarantine_reason: "adjudicated",
  adjudication_id: "adj-1",
  rescues_period: false,
}

function requestedUrl(): string {
  return String(vi.mocked(globalThis.fetch).mock.calls[0][0])
}

function requestedInit(): RequestInit {
  return vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit
}

function sentBody(): unknown {
  return JSON.parse(String(requestedInit().body))
}

describe("the adjudication calls", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    answers(ACCEPTED)
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("sends the quarantine to the quarantine route and the release to the release route", async () => {
    // The two routes are near-identical in shape and opposite in effect. A
    // swap would put a row back into the totals when someone asked for it to
    // be taken out, and the response would look like a success.
    await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Duplicate of row 44.",
    })
    expect(new URL(requestedUrl(), "http://loupe.test").pathname).toBe(
      "/api/financial/transactions/txn-1/quarantine"
    )

    vi.mocked(globalThis.fetch).mockClear()
    await financialAPI.releaseRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Confirmed against the original statement.",
    })
    expect(new URL(requestedUrl(), "http://loupe.test").pathname).toBe(
      "/api/financial/transactions/txn-1/release"
    )
  })

  it("posts, rather than reading", async () => {
    await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Duplicate of row 44.",
    })

    expect(requestedInit().method).toBe("POST")
  })

  it("names the case in the query string, under the name the endpoint reads", async () => {
    // The case is how the backend decides whether this caller may edit this
    // row at all. Sent under any other name it is absent, and the request is
    // rejected rather than misapplied -- but only because the parameter is
    // required, which is what this test is really holding in place.
    await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Duplicate of row 44.",
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({ case_id: "case-1" })
  })

  it("puts the justification in the body, wrapped under its own key", async () => {
    // The backend declares `reason` with `embed=True`, so it reads
    // `{"reason": "..."}` and not a bare string. Sent bare, FastAPI rejects the
    // request; sent in the query string it is silently absent and the write is
    // refused. Either way the row does not move and the person is told nothing
    // useful about why.
    await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Duplicate of row 44.",
    })

    expect(sentBody()).toEqual({ reason: "Duplicate of row 44." })
    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.has("reason")).toBe(false)
  })

  it("carries a justification through unaltered, whatever is in it", async () => {
    // Recorded verbatim against a named person, so it has to arrive as it was
    // written. Quotation marks and line breaks are ordinary in a note about a
    // bank statement.
    const reason = 'Row reads "1,250.00"; the statement shows 125.00.\nSee p.4.'
    await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason,
    })

    expect(sentBody()).toEqual({ reason })
  })

  it("escapes the row identifier into the path", async () => {
    await financialAPI.releaseRow({
      caseId: "case one",
      transactionId: "txn/1 2",
      reason: "Reinstated.",
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.pathname).toBe("/api/financial/transactions/txn%2F1%202/release")
    expect(url.searchParams.get("case_id")).toBe("case one")
  })

  it("returns the answer rather than reducing it to whether it worked", async () => {
    // A refusal comes back 200 carrying the refusal. If this call collapsed
    // the response to a boolean, the screen would have to describe a refusal
    // as a success, and the rescue fact below would have nowhere to live.
    answers({
      ...ACCEPTED,
      outcome: "refused",
      applied: false,
      reason: "Row is superseded.",
      ledger_status: "superseded",
      quarantine_reason: null,
      adjudication_id: null,
      rescues_period: null,
    })

    const result = await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Duplicate of row 44.",
    })

    expect(result.outcome).toBe("refused")
    expect(result.applied).toBe(false)
    expect(result.reason).toBe("Row is superseded.")
  })

  it("keeps an unknown rescue answer distinct from a negative one", async () => {
    // `null` means the question could not be answered; `false` means it was
    // answered and no gap was closed. JSON carries both, and this asserts the
    // client does not flatten one into the other on the way through.
    answers({ ...ACCEPTED, rescues_period: null })
    const unknown = await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Unreadable.",
    })
    expect(unknown.rescues_period).toBeNull()

    vi.mocked(globalThis.fetch).mockClear()
    answers({ ...ACCEPTED, rescues_period: false })
    const negative = await financialAPI.quarantineRow({
      caseId: "case-1",
      transactionId: "txn-1",
      reason: "Unreadable.",
    })
    expect(negative.rescues_period).toBe(false)
  })
})

/* ------------------------------------------------------------------ *
 * What the backend still says
 * ------------------------------------------------------------------ */

describe("the adjudication contract", () => {
  const routerSource = read(backend("routers", "financial_adjudication.py"))
  const serviceSource = read(
    backend("services", "financial", "quarantine_row.py")
  )

  it("is still mounted on the app", () => {
    // A router that is not included is a 404 on every path, and the tests
    // above would keep passing: they check what is sent, not that anything
    // answers.
    const registry = read(backend("routers", "__init__.py"))
    expect(registry).toContain(
      "from routers.financial_adjudication import router as financial_adjudication_router"
    )
  })

  it("still mounts both routes where this file posts them", () => {
    expect(routerSource).toContain('prefix="/api/financial"')
    expect(routerSource).toContain(
      '@router.post("/transactions/{transaction_id}/quarantine")'
    )
    expect(routerSource).toContain(
      '@router.post("/transactions/{transaction_id}/release")'
    )
  })

  it.each([
    ["quarantine_transaction_row", "quarantine"],
    ["release_transaction_row", "release"],
  ])("still reads case_id and an embedded reason on %s", (fn) => {
    const block = pythonBlock(routerSource, `async def ${fn}(`)
    expect(block).toContain("case_id: UUID = Query(")
    expect(block).toContain("reason: str = Body(")
    // `embed=True` is what makes the wrapped body above correct. Without it
    // FastAPI expects a bare JSON string and every write fails validation.
    expect(block).toContain("embed=True")
  })

  it("still turns only a missing row and a failed write into HTTP errors", () => {
    // Everything else -- including a refusal -- is a fact about the row's
    // standing and comes back 200. If the backend started raising on
    // `refused`, the response this file is typed to read would never arrive
    // and the reason would surface as a browser error instead of beside the
    // row.
    const respond = pythonBlock(routerSource, "def _respond(")
    expect(respond).toContain("RowAdjudicationOutcome.not_found")
    expect(respond).toContain("status_code=404")
    expect(respond).toContain("RowAdjudicationOutcome.write_failed")
    expect(respond).toContain("status_code=500")

    const raised = [...respond.matchAll(/RowAdjudicationOutcome\.(\w+)/g)].map(
      (m) => m[1]
    )
    expect(new Set(raised)).toEqual(new Set(["not_found", "write_failed"]))
  })

  it("still has exactly the outcomes this build knows how to read", () => {
    const members = enumMembers(
      serviceSource,
      "class RowAdjudicationOutcome(str, Enum):"
    )
    expect(members.sort()).toEqual([...ROW_ADJUDICATION_OUTCOMES].sort())
  })

  it("still returns exactly the fields this build declares", () => {
    // Closed in both directions: a field added to the response and not read
    // here is dropped in silence, and a field dropped from the response leaves
    // this build reading `undefined` as though it were an answer.
    const body = pythonBlock(serviceSource, "    def as_dict(self)")
    const keys = [...body.matchAll(/^ {12}"(\w+)":/gm)].map((m) => m[1])
    expect(keys.sort()).toEqual([...ROW_ADJUDICATION_FIELDS].sort())
  })

  it("still records a person's decision under grounds this build can name", () => {
    // Quarantine over HTTP always records `adjudicated`, and never a computed
    // class. The screen distinguishes the two, so the value it will actually
    // receive has to be one it has a name for.
    expect(serviceSource).toContain("QuarantineReason.adjudicated")
    expect(QUARANTINE_REASONS).toContain("adjudicated")
  })
})
