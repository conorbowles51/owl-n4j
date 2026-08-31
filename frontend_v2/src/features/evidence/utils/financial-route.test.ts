/**
 * Holds the interface's outcome vocabulary against the two services that
 * produce it.
 *
 * The first half of this file tests the module on its own terms.  The second
 * half reads the Python sources and asserts that what they can return is
 * exactly what this build claims they can return -- because a union written
 * from memory is a comment, and comments do not fail.
 *
 * Reading another language's source in a unit test is unusual and worth
 * justifying.  The alternative is a generated artefact both sides publish,
 * which is a build step, a checked-in file that can go stale between the
 * generating and the using, and a second thing to run in CI.  The vocabulary
 * here is eleven short string literals in two files that change perhaps twice a
 * year; a regex over the two `outcome` properties costs nothing and fails on
 * the same commit that introduces the drift, which is the only moment the
 * failure is cheap to fix.
 */

import { describe, expect, it } from "vitest"
import { existsSync, readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  ALL_ROUTE_OUTCOMES,
  BACKEND_ONLY_OUTCOMES,
  BLOCKING_OUTCOMES,
  ENGINE_ONLY_OUTCOMES,
  NATIVE_FORMAT_LABEL,
  ROUTE_OUTCOME_DESCRIPTION,
  ROUTE_OUTCOME_LABEL,
  ROUTE_OUTCOME_VARIANT,
  SHARED_OUTCOMES,
  belongsToLedger,
  blocksDocumentProcessing,
  coerceOutcome,
  formatLabel,
  isKnownOutcome,
  type RouteOutcome,
} from "./financial-route"

const sorted = (values: readonly string[]) => [...values].sort()

describe("the outcome union", () => {
  it("is the two services' vocabularies with the shared part counted once", () => {
    expect(sorted(ALL_ROUTE_OUTCOMES)).toEqual(
      sorted([...SHARED_OUTCOMES, ...BACKEND_ONLY_OUTCOMES, ...ENGINE_ONLY_OUTCOMES])
    )
  })

  it("has no outcome in more than one group", () => {
    const all = [...SHARED_OUTCOMES, ...BACKEND_ONLY_OUTCOMES, ...ENGINE_ONLY_OUTCOMES]
    expect(new Set(all).size).toBe(all.length)
  })

  it("gives every outcome something to show on screen", () => {
    // A `Record` lookup that misses returns `undefined`, and React renders
    // `undefined` as nothing at all -- a badge with no text is indistinguishable
    // from a file nobody checked. Typing these as `Record<RouteOutcome, ...>`
    // makes the compiler agree; this asserts it at runtime too, because the
    // value arriving from the wire is a `string` the compiler never saw.
    for (const outcome of ALL_ROUTE_OUTCOMES) {
      expect(ROUTE_OUTCOME_LABEL[outcome], `label for ${outcome}`).toBeTruthy()
      expect(ROUTE_OUTCOME_DESCRIPTION[outcome], `description for ${outcome}`).toBeTruthy()
      expect(ROUTE_OUTCOME_VARIANT[outcome], `variant for ${outcome}`).toBeTruthy()
    }
  })
})

describe("what stops a file reaching the document pipeline", () => {
  it("blocks everything except a file positively identified as a document", () => {
    // Stated as the complement on purpose. Listing the blocking outcomes again
    // here would pass by copying the mistake; asserting that `not_native` and
    // `not_found` are the *only* two that pass means a newly added outcome
    // fails this test until somebody decides which side it belongs on.
    const passes = ALL_ROUTE_OUTCOMES.filter((o) => !blocksDocumentProcessing(o))
    expect(sorted(passes)).toEqual(["not_found", "not_native"])
  })

  it("sends only a single-claimant file to the ledger", () => {
    // Narrower than blocking, and deliberately so: an ambiguous file blocks,
    // but the ledger's parser requires exactly one claimant and would fail on
    // it too, so offering the ledger as the remedy would be a dead end.
    const ledgerBound = ALL_ROUTE_OUTCOMES.filter(belongsToLedger)
    expect(ledgerBound).toEqual(["native"])
  })

  it("blocks every outcome that means the answer is not known", () => {
    const uncertain: RouteOutcome[] = ["ambiguous", "unreadable", "undetermined", "detector_unavailable"]
    for (const outcome of uncertain) {
      expect(blocksDocumentProcessing(outcome), `${outcome} must block`).toBe(true)
    }
  })
})

describe("outcomes arriving from a service newer than this build", () => {
  it("recognises the ones it was built with", () => {
    for (const outcome of ALL_ROUTE_OUTCOMES) {
      expect(isKnownOutcome(outcome)).toBe(true)
    }
  })

  it("does not recognise a word it has never seen", () => {
    expect(isKnownOutcome("quarantined")).toBe(false)
    expect(isKnownOutcome("")).toBe(false)
    expect(isKnownOutcome("NATIVE")).toBe(false)
  })

  it("turns an unknown outcome into one that blocks", () => {
    // The failure being guarded against is a bank file read as prose. Falling
    // back to `not_native` would make every outcome invented after this build
    // a green light, which is exactly the wrong direction to fail in.
    expect(coerceOutcome("quarantined")).toBe("undetermined")
    expect(blocksDocumentProcessing(coerceOutcome("quarantined"))).toBe(true)
  })

  it("leaves a known outcome alone", () => {
    for (const outcome of ALL_ROUTE_OUTCOMES) {
      expect(coerceOutcome(outcome)).toBe(outcome)
    }
  })
})

describe("native format labels", () => {
  it("writes the four formats the way a bank writes them", () => {
    expect(formatLabel("camt053")).toBe("camt.053")
    expect(formatLabel("bai2")).toBe("BAI2")
    expect(formatLabel("mt940")).toBe("MT940")
    expect(formatLabel("nacha")).toBe("NACHA")
  })

  it("shows an unrecognised format code rather than nothing", () => {
    // A format this build has no label for is still a fact about the file, and
    // the raw code is more use on screen than an empty space.
    expect(formatLabel("iso20022_pain")).toBe("iso20022_pain")
  })
})

// --------------------------------------------------------------------------
// Drift: the union against the sources that produce it
// --------------------------------------------------------------------------

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../..")
const BACKEND_ROUTE_CHECK = resolve(repoRoot, "backend/services/financial/route_check.py")
const ENGINE_ROUTE = resolve(repoRoot, "evidence-engine/app/pipeline/financial_route.py")

/**
 * The body of a Python method, found by indentation rather than by brace.
 *
 * Bounded by the first later line that is non-blank and indented no further
 * than the `def` itself, which ends the method whether what follows is another
 * method, a decorator, or a module-level function -- the last of which is the
 * case in the engine, where `outcome` is the final method in its class.
 */
function pythonMethodBody(source: string, name: string): string {
  const lines = source.split("\n")
  const start = lines.findIndex((line) => new RegExp(`^(\\s*)def ${name}\\b`).test(line))
  if (start === -1) throw new Error(`no def ${name} in source`)
  const indent = lines[start].length - lines[start].trimStart().length
  const body: string[] = []
  for (const line of lines.slice(start + 1)) {
    if (line.trim() === "") {
      body.push(line)
      continue
    }
    if (line.length - line.trimStart().length <= indent) break
    body.push(line)
  }
  return body.join("\n")
}

/** Every string a `return "..."` in this snippet can produce. */
function returnedStrings(body: string): string[] {
  return [...body.matchAll(/return\s+"([^"]+)"/g)].map((match) => match[1])
}

const sourcesPresent = existsSync(BACKEND_ROUTE_CHECK) && existsSync(ENGINE_ROUTE)

// Guarded rather than assumed. `actions/checkout` gives CI the whole repository,
// so these resolve there; a checkout of this directory alone would not have
// them, and a suite that throws on a missing sibling service is worse than one
// that says plainly which assertions it could not make.
describe.runIf(sourcesPresent)("the services' own vocabularies", () => {
  it("the backend can return exactly the shared and backend-only outcomes", () => {
    const outcomes = returnedStrings(
      pythonMethodBody(readFileSync(BACKEND_ROUTE_CHECK, "utf8"), "outcome")
    )
    expect(sorted(outcomes)).toEqual(sorted([...SHARED_OUTCOMES, ...BACKEND_ONLY_OUTCOMES]))
  })

  it("the engine can return exactly the shared and engine-only outcomes", () => {
    const outcomes = returnedStrings(
      pythonMethodBody(readFileSync(ENGINE_ROUTE, "utf8"), "outcome")
    )
    expect(sorted(outcomes)).toEqual(sorted([...SHARED_OUTCOMES, ...ENGINE_ONLY_OUTCOMES]))
  })

  it("neither service alone can produce the whole union", () => {
    // The reason the union lives in this package rather than being shared
    // server-side: `detector_unavailable` means the backend package could not
    // be imported, so it cannot be defined there, and `not_found` is a question
    // about a case that the engine never asks.
    expect(BACKEND_ONLY_OUTCOMES.length).toBeGreaterThan(0)
    expect(ENGINE_ONLY_OUTCOMES.length).toBeGreaterThan(0)
  })

  it("blocks everything the backend blocks", () => {
    const line = readFileSync(BACKEND_ROUTE_CHECK, "utf8")
      .split("\n")
      .find((candidate) => candidate.startsWith("BLOCKING_OUTCOMES"))
    expect(line, "backend BLOCKING_OUTCOMES is no longer a module-level literal").toBeTruthy()
    const backendBlocking = [...(line as string).matchAll(/"([^"]+)"/g)].map((m) => m[1])

    // A superset, not an equality: the backend cannot block an outcome it has
    // no way to return, and `detector_unavailable` is the engine's word for
    // "nothing was checked at all", which must block here even though the
    // endpoint that answers this screen will never say it.
    for (const outcome of backendBlocking) {
      expect(BLOCKING_OUTCOMES, `backend blocks ${outcome}`).toContain(outcome)
    }
    const extra = BLOCKING_OUTCOMES.filter((o) => !backendBlocking.includes(o))
    expect(extra).toEqual(["detector_unavailable"])
  })
})

/**
 * The body of a Python class, bounded the same way {@link pythonMethodBody}
 * bounds a method.
 */
function pythonClassBody(source: string, name: string): string {
  const lines = source.split("\n")
  const start = lines.findIndex((line) => new RegExp(`^(\\s*)class ${name}\\b`).test(line))
  if (start === -1) throw new Error(`no class ${name} in source`)
  const indent = lines[start].length - lines[start].trimStart().length
  const body: string[] = []
  for (const line of lines.slice(start + 1)) {
    if (line.trim() === "") {
      body.push(line)
      continue
    }
    if (line.length - line.trimStart().length <= indent) break
    body.push(line)
  }
  return body.join("\n")
}

describe.runIf(sourcesPresent)("native format codes", () => {
  it("labels every format the detector can claim", () => {
    // `NATIVE_FORMAT_LABEL` is keyed on `NativeFormat`'s values, and a format
    // added there without a label here renders a bare code like `camt053` on
    // screen next to three that are written the way a bank writes them.
    const nativePy = resolve(repoRoot, "backend/services/financial/native.py")
    expect(existsSync(nativePy), `expected the detector at ${nativePy}`).toBe(true)

    const body = pythonClassBody(readFileSync(nativePy, "utf8"), "NativeFormat")
    const enumValues = [...body.matchAll(/^\s+\w+\s*=\s*"([^"]+)"/gm)].map((match) => match[1])

    // Asserted rather than tolerated. An empty list here would mean the regex
    // stopped matching -- the members are lower case, which a pattern written
    // for the usual SHOUTING enum silently misses -- and a loop over nothing
    // passes while checking nothing.
    expect(enumValues.length, "found no members of NativeFormat").toBeGreaterThan(0)

    for (const value of enumValues) {
      expect(NATIVE_FORMAT_LABEL, `label for detector format ${value}`).toHaveProperty(value)
    }
  })
})
