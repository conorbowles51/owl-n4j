/**
 * The ledger read, and the contract it depends on.
 *
 * Two kinds of test here. The first kind checks what this file sends: a
 * request that quietly drops a filter returns more rows than were asked for,
 * and on a money screen that is not a cosmetic fault.
 *
 * The second kind reads the backend source and requires the two languages to
 * still agree. The relational ledger is written by Python and read by
 * TypeScript, and nothing between them will notice if one side moves: a
 * renamed query parameter is accepted and ignored by FastAPI, a new column on
 * the read shape simply never appears, and a new member of a closed vocabulary
 * arrives as a string this build has no name for. Each of those failures is
 * silent, and each of them is silent in the direction of showing a figure that
 * looks complete and is not.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  DATE_SOURCES,
  LEDGER_STATUSES,
  LEDGER_TRANSACTION_FIELDS,
  PROOF_CLASSES,
  QUARANTINE_REASONS,
  TRANSACTION_DIRECTIONS,
  financialAPI,
  type LedgerTransaction,
} from "./api"

const here = dirname(fileURLToPath(import.meta.url))
const backend = (...parts: string[]) =>
  resolve(here, "../../../../backend", ...parts)

function read(path: string): string {
  return readFileSync(path, "utf8")
}

/**
 * The body of a Python block, from its header to the next line that starts in
 * column one. Scoping matters: a whole-file search for a member name passes on
 * an identical member of a different enum, and every vocabulary below shares
 * members with at least one other.
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

describe("financialAPI.getLedgerTransactions", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ case_id: "case-1", transactions: [], total: 0 })
    )
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("asks the ledger endpoint, not the graph one", async () => {
    // `/api/financial` and `/api/financial/ledger` read different stores. A
    // request that lands on the first one returns a plausible list of
    // transactions with none of the provenance this screen exists to show.
    await financialAPI.getLedgerTransactions({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.pathname).toBe("/api/financial/ledger")
  })

  it("sends no status of its own when none was asked for", async () => {
    // The endpoint defaults to `admitted`, the population every total is
    // filtered to. If this function sent a default instead, the two defaults
    // could drift apart and the screen would quietly stop agreeing with the
    // totals it sits beside.
    await financialAPI.getLedgerTransactions({ caseId: "case-1" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.has("ledger_status")).toBe(false)
  })

  it("sends every filter it was given, under the names the endpoint reads", async () => {
    await financialAPI.getLedgerTransactions({
      caseId: "case-1",
      accountId: "account-9",
      ledgerStatus: "quarantined",
      startDate: "2024-01-01",
      endDate: "2024-03-31",
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      case_id: "case-1",
      account_id: "account-9",
      ledger_status: "quarantined",
      start_date: "2024-01-01",
      end_date: "2024-03-31",
    })
  })

  it("escapes values rather than pasting them into the query string", async () => {
    // Built with URLSearchParams rather than by concatenation. A case id that
    // arrived with an ampersand in it would otherwise split into two
    // parameters and the request would be answered for a different case.
    await financialAPI.getLedgerTransactions({ caseId: "a&ledger_status=rejected" })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("case_id")).toBe("a&ledger_status=rejected")
    expect(url.searchParams.has("ledger_status")).toBe(false)
  })

  it("returns the rows the endpoint sent", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({
        case_id: "case-1",
        transactions: [{ key: "row-1" }],
        total: 1,
      })
    )

    const result = await financialAPI.getLedgerTransactions({ caseId: "case-1" })
    expect(result.total).toBe(1)
    expect(result.transactions).toHaveLength(1)
  })
})

/* ------------------------------------------------------------------ *
 * What the backend actually offers
 * ------------------------------------------------------------------ */

describe("the ledger endpoint contract", () => {
  const router = () => read(backend("routers/financial_ledger.py"))

  it("is still mounted where this file asks for it", () => {
    const source = router()
    expect(source).toMatch(/prefix\s*=\s*"\/api\/financial"/)
    expect(source).toMatch(/@router\.get\("\/ledger"\)/)
  })

  it("still reads every parameter this file sends", () => {
    // Scoped to the endpoint's own signature. FastAPI ignores a parameter it
    // was not told about without complaint, so a rename on that side would
    // drop a filter here and answer with more rows than were asked for --
    // which looks like a fuller ledger rather than like a broken request.
    const source = router()
    const decorator = '@router.get("/ledger")'
    const opens = source.indexOf(decorator)
    expect(opens, "the ledger endpoint is no longer declared").toBeGreaterThan(-1)

    const next = source.indexOf("\n@router.", opens + decorator.length)
    const body = next === -1 ? source.slice(opens) : source.slice(opens, next)
    for (const param of [
      "case_id",
      "account_id",
      "ledger_status",
      "start_date",
      "end_date",
    ]) {
      expect(body, `${param} is no longer a parameter of GET /ledger`).toMatch(
        new RegExp(`^\\s{4}${param}:`, "m")
      )
    }
  })

  it("still answers with the envelope this file unwraps", () => {
    const source = router()
    expect(source).toMatch(/"case_id":\s*str\(case_id\)/)
    expect(source).toMatch(/"transactions":\s*transactions/)
    expect(source).toMatch(/"total":\s*len\(transactions\)/)
  })
})

describe("the ledger row shape", () => {
  it("declares exactly the fields the backend emits", () => {
    // Read off `TransactionView.to_json`, which is what the endpoint returns
    // for every row. A field added there and not here is not a compile error
    // on either side; it is simply a fact about the row that never reaches
    // anyone.
    const source = read(backend("services/financial/transaction_query.py"))
    const body = pythonBlock(source, "    def to_json(self)")
    const emitted = [...body.matchAll(/"([a-z_0-9]+)":\s*self\./g)].map((m) => m[1])

    expect(emitted.length).toBeGreaterThan(0)
    expect(new Set(emitted)).toEqual(new Set(LEDGER_TRANSACTION_FIELDS))
  })

  it("lists every field the interface declares", () => {
    // The list is typed `keyof LedgerTransaction`, so it cannot name a field
    // the interface does not have. This closes the other direction at compile
    // time: if a field is declared and left off the list, the type below is
    // `false` and the assignment stops building.
    const everyDeclaredFieldIsListed: [
      Exclude<keyof LedgerTransaction, (typeof LEDGER_TRANSACTION_FIELDS)[number]>,
    ] extends [never]
      ? true
      : false = true

    expect(everyDeclaredFieldIsListed).toBe(true)
  })
})

describe("the closed vocabularies", () => {
  const enums = () => read(backend("postgres/models/enums.py"))

  // Each of these is a set this build renders a label for. A member added on
  // the backend and not here reaches the screen as a value with no name, which
  // `ledger-format.ts` will mark as unrecognised rather than show blank -- but
  // marking it is a fallback, not the intended state, and this is what says so.

  it("ledger status still has the members this build knows", () => {
    expect(enumMembers(enums(), "class LedgerStatus(str, Enum):")).toEqual([
      ...LEDGER_STATUSES,
    ])
  })

  it("proof class still has the members this build knows", () => {
    expect(enumMembers(enums(), "class ProofClass(str, Enum):")).toEqual([
      ...PROOF_CLASSES,
    ])
  })

  it("transaction direction still has the members this build knows", () => {
    expect(enumMembers(enums(), "class TransactionDirection(str, Enum):")).toEqual([
      ...TRANSACTION_DIRECTIONS,
    ])
  })

  it("date source still has the members this build knows", () => {
    expect(enumMembers(enums(), "class DateSource(str, Enum):")).toEqual([
      ...DATE_SOURCES,
    ])
  })

  it("quarantine reason still has the members this build knows", () => {
    expect(enumMembers(enums(), "class QuarantineReason(str, Enum):")).toEqual([
      ...QUARANTINE_REASONS,
    ])
  })

  it("extraction layer still runs from 0 to 3", () => {
    // An int enum rather than a string one, and the ledger stores the int, so
    // it is read from the column constraint that the writer has to satisfy.
    const model = read(backend("postgres/models/financial.py"))
    expect(model).toMatch(
      /"extraction_layer BETWEEN 0 AND 3",\s*\n\s*name="ck_financial_transactions_extraction_layer"/
    )
  })
})
