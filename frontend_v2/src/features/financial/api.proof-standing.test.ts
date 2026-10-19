/**
 * The proof class census, and the contract it depends on.
 *
 * The same two kinds of test as `api.decisions.test.ts`: what this file sends,
 * and whether the backend still offers what it is asking for. The census is
 * computed in Python and read in TypeScript, and nothing between them notices
 * if one side moves.
 *
 * What makes this read different from the other three, and what most of the
 * tests below are holding in place:
 *
 * **The permissions are the payload, not decoration.** `p3` is two characters
 * that mean nothing on their own. The fact they name -- that this is the one
 * class no ingestion run admits by itself -- arrives only in
 * `requires_adjudication`, and if that field stops arriving the counts keep
 * coming and every screen goes on rendering, showing material that nobody has
 * ruled on as though it were part of the verified ledger. That failure is
 * invisible from the screen, so it has to be caught here.
 *
 * **It is a census, so the parts add up to the whole.** Any filter reaching the
 * endpoint from this side would break that while the response looked identical.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  CLASS_STANDING_FIELDS,
  PROOF_CLASSES,
  PROOF_STANDING_FIELDS,
  financialAPI,
} from "./api"

const here = dirname(fileURLToPath(import.meta.url))
const backend = (...parts: string[]) =>
  resolve(here, "../../../../backend", ...parts)

function read(path: string): string {
  return readFileSync(path, "utf8")
}

/** From a declaration at column zero to the next one. See `api.ledger.test.ts`. */
function pythonBlock(source: string, header: string): string {
  const opens = source.indexOf(header)
  expect(opens, `${header} is no longer declared`).toBeGreaterThan(-1)
  const rest = source.slice(opens + header.length)
  const next = rest.search(/\n(?=\S)/)
  return next === -1 ? rest : rest.slice(0, next)
}

/** The keys one class's `as_dict` puts on the wire. */
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

const emptyCensus = {
  case_id: "case-1",
  classes: [],
  documents: 0,
  transactions: 0,
  documents_requiring_adjudication: 0,
  transactions_requiring_adjudication: 0,
  counted_classes: ["p0", "p1", "p2"],
}

describe("financialAPI.getCaseProofStanding", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(emptyCensus))
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("asks the proof standing endpoint, not the ledger or decisions one", async () => {
    await financialAPI.getCaseProofStanding("case-1")

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.pathname).toBe("/api/financial/proof-standing")
  })

  it("sends the case and nothing else", async () => {
    // A filter of any kind would make the per-class figures stop adding up to
    // the case's documents and rows, which is the property that lets a reader
    // check the breakdown at all. The response would look identical.
    await financialAPI.getCaseProofStanding("case-1")

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({ case_id: "case-1" })
  })

  it("escapes the case rather than pasting it into the query string", async () => {
    await financialAPI.getCaseProofStanding("a&ledger_status=admitted")

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.searchParams.get("case_id")).toBe("a&ledger_status=admitted")
    expect(url.searchParams.has("ledger_status")).toBe(false)
  })

  it("hands back the census whole, permissions included", async () => {
    // Not the counts alone. A caller that reshaped this would be free to drop
    // the four booleans, leaving numbers against labels no reader can
    // interpret.
    const census = {
      case_id: "case-1",
      classes: [
        {
          proof_class: "p3",
          documents: 2,
          transactions: 7,
          admits_automatically: false,
          requires_adjudication: true,
          may_produce_ledger_rows: true,
          counts_toward_totals: false,
        },
      ],
      documents: 2,
      transactions: 7,
      documents_requiring_adjudication: 2,
      transactions_requiring_adjudication: 7,
      counted_classes: ["p0", "p1", "p2"],
    }
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(census))

    const result = await financialAPI.getCaseProofStanding("case-1")
    expect(result).toEqual(census)
  })
})

/* ------------------------------------------------------------------ *
 * What the backend actually offers
 * ------------------------------------------------------------------ */

describe("the proof standing endpoint contract", () => {
  const router = () => read(backend("routers/financial_ledger.py"))

  it("is still mounted where this file asks for it", () => {
    const source = router()
    expect(source).toMatch(/prefix\s*=\s*"\/api\/financial"/)
    expect(source).toMatch(/@router\.get\("\/proof-standing"\)/)
  })

  it("is still on the router that resolves to a view permission", () => {
    // A census of what a case holds needs no more permission than reading the
    // rows does. If this ever moved to the adjudication router it would start
    // demanding the permission to change the ledger in order to describe it.
    const source = router()
    expect(source).toMatch(/return \("case", "view"\)/)
    expect(routeBody(source, '@router.get("/proof-standing")')).not.toMatch(
      /case_access_dependency/
    )
  })

  it("still takes the case and nothing else", () => {
    // This is what makes "send only case_id" the right behaviour on this side.
    // A filter appearing on the route is the moment this file would need to
    // decide what to send for it, and the honest default is not obvious.
    const body = routeBody(router(), '@router.get("/proof-standing")')
    // The signature only, from `async def` to the line that closes it. Scoped
    // because the body has indented `name:` lines of its own -- a `try:` reads
    // as a parameter to a regex that is not told where the signature ends.
    const closes = body.indexOf("\n):")
    expect(closes, "the route signature no longer closes at column zero")
      .toBeGreaterThan(-1)
    const signature = body.slice(body.indexOf("async def"), closes)
    const params = [...signature.matchAll(/^ {4}(\w+):/gm)].map((m) => m[1])
    expect(params).toEqual(["case_id", "db"])
  })

  it("still answers with the whole census rather than a rebuilt one", () => {
    const body = routeBody(router(), '@router.get("/proof-standing")')
    expect(body).toMatch(/return standing\.as_dict\(\)/)
  })

  it("still leaves the counted set to the backend", () => {
    // Not a parameter, deliberately. A screen that could choose its own set
    // would be free to show a coverage the totals beside it were never
    // computed against.
    const body = routeBody(router(), '@router.get("/proof-standing")')
    expect(body).not.toMatch(/included/)
  })
})

describe("the census shape", () => {
  const standing = () => read(backend("services/financial/proof_standing.py"))

  it("declares exactly the class fields the backend emits", () => {
    const body = pythonBlock(standing(), "class ClassStanding:")
    const emitted = emittedKeys(body)

    expect(emitted.length).toBeGreaterThan(0)
    expect(new Set(emitted)).toEqual(new Set(CLASS_STANDING_FIELDS))
  })

  it("declares exactly the envelope fields the backend emits", () => {
    const body = pythonBlock(standing(), "class ProofStanding:")
    const emitted = emittedKeys(body)

    expect(emitted.length).toBeGreaterThan(0)
    expect(new Set(emitted)).toEqual(new Set(PROOF_STANDING_FIELDS))
  })

  it("still names requires_adjudication, which is why this read exists", () => {
    // Stated on its own rather than left to the set comparison above. The
    // permission this field carries is the one a reader cannot recover from
    // the label, and a rename that happened to keep the field count right
    // would otherwise pass.
    expect(CLASS_STANDING_FIELDS).toContain("requires_adjudication")
    expect(standing()).toMatch(/"requires_adjudication": self\.requires_adjudication/)
  })

  it("still reports every class rather than only the occupied ones", () => {
    // A class holding nothing reports zero. "No p3 documents here" and
    // "nothing looked at p3" are different facts and an absent key spells them
    // the same way, so anything rendering this counts on all five arriving.
    expect(standing()).toMatch(/for member in ProofClass/)
  })

  it("still takes its permissions from proof_class rather than restating them", () => {
    // If this module ever computed the four booleans itself, they could
    // disagree with the rules the ledger actually enforces, and the
    // disagreement would surface as material shown as verified that is not.
    const source = standing()
    for (const predicate of [
      "admits_automatically",
      "requires_adjudication",
      "may_produce_ledger_rows",
      "counts_toward_totals",
    ]) {
      expect(source).toMatch(
        new RegExp(`from services\\.financial\\.proof_class import[\\s\\S]{0,300}${predicate}`)
      )
    }
  })
})

describe("the class vocabulary", () => {
  it("still matches the backend enum", () => {
    // `api.ledger.test.ts` pins this too. Repeated here because this read is
    // the only one that reports a row for every member: a class added in
    // Python and not here arrives as a standing this build cannot label.
    const enums = read(backend("postgres/models/enums.py"))
    const block = pythonBlock(enums, "class ProofClass(str, Enum):")
    const members = [...block.matchAll(/^ {4}(\w+) = "([^"]*)"/gm)].map((m) => m[2])

    expect(members).toEqual([...PROOF_CLASSES])
  })
})
