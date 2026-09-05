/**
 * The runs read, and the contract it depends on.
 *
 * Same two kinds of test as `api.ledger.test.ts`, and for the same reason: the
 * runs are written by Python and read by TypeScript, and nothing between the
 * two will notice if one side moves.
 *
 * One difference is worth stating outright. The ledger read defaults to
 * `admitted`, so a dropped filter there shows *more* than was asked for. The
 * runs read defaults to every status, so a filter that leaks in here shows
 * *less* -- and the rows it would drop first are the failed and aborted ones,
 * which are the entire reason anyone opens this list. Several of the tests
 * below exist to hold that default in place on both sides of the wire.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  INGESTION_RUN_FIELDS,
  INGESTION_RUN_STATUSES,
  financialAPI,
  type IngestionRun,
} from "./api"

const here = dirname(fileURLToPath(import.meta.url))
const backend = (...parts: string[]) =>
  resolve(here, "../../../../backend", ...parts)

function read(path: string): string {
  return readFileSync(path, "utf8")
}

/** See `api.ledger.test.ts`: scoped so an identical member of a different enum cannot pass. */
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

describe("financialAPI.getIngestionRuns", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ case_id: "case-1", runs: [], total: 0 })
    )
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("asks the runs endpoint, not the ledger one", async () => {
    await financialAPI.getIngestionRuns({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.pathname).toBe("/api/financial/runs")
  })

  it("sends no status of its own when none was asked for", async () => {
    // The endpoint defaults to every status. A default sent from here could
    // drift from that one, and the first thing a drifted default would hide is
    // a failed run -- which is what this read exists to show.
    await financialAPI.getIngestionRuns({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.has("status")).toBe(false)
    expect(Object.fromEntries(url.searchParams)).toEqual({ case_id: "case-1" })
  })

  it("sends every filter it was given, under the names the endpoint reads", async () => {
    await financialAPI.getIngestionRuns({
      caseId: "case-1",
      status: "failed",
      limit: 20,
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      case_id: "case-1",
      status: "failed",
      limit: "20",
    })
  })

  it("sends a limit of zero rather than dropping it", async () => {
    // `if (params.limit)` would swallow 0 and silently return every run for a
    // caller who asked for none. The backend refuses 0 with a 400, which is the
    // answer that caller should get.
    await financialAPI.getIngestionRuns({ caseId: "case-1", limit: 0 })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("limit")).toBe("0")
  })

  it("escapes values rather than pasting them into the query string", async () => {
    await financialAPI.getIngestionRuns({ caseId: "a&status=completed" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("case_id")).toBe("a&status=completed")
    expect(url.searchParams.has("status")).toBe(false)
  })

  it("returns the runs the endpoint sent", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ case_id: "case-1", runs: [{ key: "run-1" }], total: 1 })
    )

    const result = await financialAPI.getIngestionRuns({ caseId: "case-1" })
    expect(result.total).toBe(1)
    expect(result.runs).toHaveLength(1)
  })
})

/* ------------------------------------------------------------------ *
 * What the backend actually offers
 * ------------------------------------------------------------------ */

describe("the runs endpoint contract", () => {
  const router = () => read(backend("routers/financial_ledger.py"))

  it("is still mounted where this file asks for it", () => {
    const source = router()
    expect(source).toMatch(/prefix\s*=\s*"\/api\/financial"/)
    expect(source).toMatch(/@router\.get\("\/runs"\)/)
  })

  it("still reads every parameter this file sends", () => {
    const source = router()
    const decorator = '@router.get("/runs")'
    const opens = source.indexOf(decorator)
    expect(opens, "the runs endpoint is no longer declared").toBeGreaterThan(-1)

    const next = source.indexOf("\n@router.", opens + decorator.length)
    const body = next === -1 ? source.slice(opens) : source.slice(opens, next)
    for (const param of ["case_id", "status", "limit"]) {
      expect(body, `${param} is no longer a parameter of GET /runs`).toMatch(
        new RegExp(`^\\s{4}${param}:`, "m")
      )
    }
  })

  it("still defaults to every status rather than to one", () => {
    // The whole design of this screen rests on it. If the endpoint acquired a
    // default the way `/ledger` has one, a request that sends no status would
    // start answering "what worked" while looking like it answered "what
    // happened", and nothing on this side would notice.
    const source = router()
    const decorator = '@router.get("/runs")'
    const opens = source.indexOf(decorator)
    const next = source.indexOf("\n@router.", opens + decorator.length)
    const body = next === -1 ? source.slice(opens) : source.slice(opens, next)

    expect(body).toMatch(/^\s{4}status: Optional\[str\] = Query\(\s*\n\s*None,/m)
    expect(body).toMatch(/status=run_status/)
    expect(body).toMatch(/run_status: Optional\[IngestionRunStatus\] = None/)
  })

  it("still answers with the envelope this file unwraps", () => {
    const source = router()
    expect(source).toMatch(/"case_id":\s*str\(case_id\)/)
    expect(source).toMatch(/"runs":\s*runs/)
    expect(source).toMatch(/"total":\s*len\(runs\)/)
  })
})

describe("the run row shape", () => {
  it("declares exactly the fields the backend emits", () => {
    // Read off `RunView.to_json`, which is what the endpoint returns for every
    // run. A field added there and not here is not a compile error on either
    // side; it is a fact about the attempt that never reaches anyone.
    const source = read(backend("services/financial/run_query.py"))
    const body = pythonBlock(source, "    def to_json(self)")
    const emitted = [...body.matchAll(/"([a-z_0-9]+)":\s*self\./g)].map((m) => m[1])

    expect(emitted.length).toBeGreaterThan(0)
    expect(new Set(emitted)).toEqual(new Set(INGESTION_RUN_FIELDS))
  })

  it("lists every field the interface declares", () => {
    // Typed `keyof IngestionRun`, so the list cannot name a field the interface
    // does not have. This closes the other direction at compile time.
    const everyDeclaredFieldIsListed: [
      Exclude<keyof IngestionRun, (typeof INGESTION_RUN_FIELDS)[number]>,
    ] extends [never]
      ? true
      : false = true

    expect(everyDeclaredFieldIsListed).toBe(true)
  })

  it("still orders newest first, with a tiebreak that makes the order total", () => {
    // Two runs opened in the same instant would otherwise come back in whatever
    // order the database felt like, and a list that reshuffles between two
    // reads of the same case cannot be cited.
    const source = read(backend("services/financial/run_query.py"))
    expect(source).toMatch(
      /FinancialIngestionRun\.started_at\.desc\(\),\s*\n\s*FinancialIngestionRun\.id\.asc\(\),/
    )
  })
})

describe("the run status vocabulary", () => {
  it("still has the members this build knows", () => {
    const source = read(backend("postgres/models/enums.py"))
    expect(enumMembers(source, "class IngestionRunStatus(str, Enum):")).toEqual([
      ...INGESTION_RUN_STATUSES,
    ])
  })
})
