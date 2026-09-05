/**
 * The words the two ingestion endpoints answer with, and the two ways this
 * module could fail quietly.
 *
 * The first failure is a missing member. `Badge` falls through to `default`
 * for a variant map that does not carry a key, and `default` is a loud filled
 * primary, so an outcome nobody wrote copy for would arrive on the screen
 * looking like the most important thing on it. The compiler catches a gap in a
 * `Record<Outcome, ...>`, but only for a member this build knows about, which
 * is why the tests below walk the vocabulary arrays themselves rather than a
 * list written out again here: a member added to `api.ts` and forgotten
 * everywhere else has to fail somewhere.
 *
 * The second is a word from a backend one version ahead. That is not an error
 * and must not render as a blank badge, because a blank badge reads as an
 * answer. It has to say, in the label, that it was not recognised.
 *
 * `wouldStore` and `didStore` are one line each and are tested anyway, because
 * what they must not do is recompute the answer from the outcome word. The
 * cases below pin the two combinations that would catch it.
 */

import { describe, expect, it } from "vitest"

import {
  INGEST_OUTCOMES,
  PRECHECK_OUTCOMES,
  type IngestOutcome,
  type PrecheckOutcome,
} from "../api"
import {
  INGEST_OUTCOME_VARIANT,
  PRECHECK_OUTCOME_VARIANT,
  accountLabel,
  didStore,
  formatPeriodRange,
  ingestVariant,
  precheckVariant,
  readIngestOutcome,
  readPrecheckOutcome,
  wouldStore,
} from "./ingest-format"

describe("readPrecheckOutcome", () => {
  it("has copy for every word the endpoint can answer with", () => {
    for (const outcome of PRECHECK_OUTCOMES) {
      const term = readPrecheckOutcome(outcome)
      expect(term.value).toBe(outcome)
      expect(term.label.length).toBeGreaterThan(0)
      // A description that merely restated the label would leave the reader
      // no better off than the raw word did.
      expect(term.description.length).toBeGreaterThan(term.label.length)
      expect(term.label).not.toContain("Unrecognised")
    }
  })

  it("says so when the word is one this build has never heard of", () => {
    const term = readPrecheckOutcome("quarantined_by_the_future")
    expect(term.value).toBeNull()
    expect(term.raw).toBe("quarantined_by_the_future")
    expect(term.label).toContain("quarantined_by_the_future")
    // Named as coming from the reading rather than from the ledger, because
    // no row was written and pointing at the ledger would send someone to
    // look for one.
    expect(term.description).toContain("the reading")
  })
})

describe("readIngestOutcome", () => {
  it("has copy for every word the endpoint can answer with", () => {
    for (const outcome of INGEST_OUTCOMES) {
      const term = readIngestOutcome(outcome)
      expect(term.value).toBe(outcome)
      expect(term.label.length).toBeGreaterThan(0)
      expect(term.description.length).toBeGreaterThan(term.label.length)
      expect(term.label).not.toContain("Unrecognised")
    }
  })

  it("does not report a good answer as a failure", () => {
    // `already_ingested` is the one that invites the mistake. Nothing was
    // stored, and that is the correct outcome, not a fault.
    const term = readIngestOutcome("already_ingested")
    expect(term.label).toBe("Already in the ledger")
    expect(INGEST_OUTCOME_VARIANT.already_ingested).not.toBe("danger")
  })

  it("says so when the word is one this build has never heard of", () => {
    const term = readIngestOutcome("stored_sideways")
    expect(term.value).toBeNull()
    expect(term.label).toContain("stored_sideways")
    expect(term.description).toContain("the ledger")
  })
})

describe("outcome badges", () => {
  it("gives every precheck outcome a variant that is not the loud fallback", () => {
    for (const outcome of PRECHECK_OUTCOMES) {
      const variant = PRECHECK_OUTCOME_VARIANT[outcome]
      expect(variant).toBeDefined()
      // `default` is what an unmapped key would silently produce, so a member
      // mapped to it explicitly is indistinguishable from one that was
      // forgotten.
      expect(variant).not.toBe("default")
      expect(precheckVariant(readPrecheckOutcome(outcome))).toBe(variant)
    }
  })

  it("gives every ingest outcome a variant that is not the loud fallback", () => {
    for (const outcome of INGEST_OUTCOMES) {
      const variant = INGEST_OUTCOME_VARIANT[outcome]
      expect(variant).toBeDefined()
      expect(variant).not.toBe("default")
      expect(ingestVariant(readIngestOutcome(outcome))).toBe(variant)
    }
  })

  it("keeps an unrecognised word quiet rather than letting it shout", () => {
    expect(precheckVariant(readPrecheckOutcome("no_such_word"))).toBe("outline")
    expect(ingestVariant(readIngestOutcome("no_such_word"))).toBe("outline")
  })

  it("colours the outcomes that stop a write differently from the one that does not", () => {
    expect(PRECHECK_OUTCOME_VARIANT.readable).toBe("success")
    expect(INGEST_OUTCOME_VARIANT.stored).toBe("success")
    expect(INGEST_OUTCOME_VARIANT.write_failed).toBe("danger")
  })
})

describe("wouldStore and didStore", () => {
  it("read the endpoint's own flag rather than judging the word", () => {
    // The pairing that matters: a word this build does not know, with a flag
    // that says the endpoint would store it. Recomputing from the word would
    // hide the button on a file the backend is willing to take.
    expect(wouldStore({ would_ingest: true })).toBe(true)
    expect(wouldStore({ would_ingest: false })).toBe(false)
    expect(didStore({ stored: true })).toBe(true)
    // `already_ingested` reports `stored: false` and is not a failure. The
    // flag is about this write, not about whether the case holds the rows.
    expect(didStore({ stored: false })).toBe(false)
  })
})

describe("formatPeriodRange", () => {
  it("reads both ends when the file printed both", () => {
    expect(formatPeriodRange("2024-01-01", "2024-03-31")).toBe(
      "2024-01-01 to 2024-03-31"
    )
  })

  it("does not leave a blank where a date was never printed", () => {
    // A blank on one side reads as an open period. The file did not say the
    // period was open; it said nothing.
    expect(formatPeriodRange("2024-01-01", null)).toBe("2024-01-01 onwards")
    expect(formatPeriodRange(null, "2024-03-31")).toBe("up to 2024-03-31")
  })

  it("says nothing at all when the file printed neither", () => {
    expect(formatPeriodRange(null, null)).toBeNull()
  })
})

describe("accountLabel", () => {
  const account = (overrides: Partial<Parameters<typeof accountLabel>[0]>) => ({
    identifier_as_printed: null,
    account_key: null,
    holder_name: null,
    ...overrides,
  })

  it("prefers what the statement printed over the internal key", () => {
    expect(
      accountLabel(
        account({ identifier_as_printed: "****4021", account_key: "acct-a" })
      )
    ).toBe("****4021")
  })

  it("names the holder alongside the number when the file gives both", () => {
    expect(
      accountLabel(
        account({ identifier_as_printed: "****4021", holder_name: "R Mensah" })
      )
    ).toBe("****4021 (R Mensah)")
  })

  it("falls back to the key so two accounts stay distinguishable", () => {
    // Not "unknown", which would make every unnamed account read alike on a
    // list whose whole job is to tell them apart.
    expect(accountLabel(account({ account_key: "acct-b" }))).toBe("acct-b")
  })

  it("says the file did not name it rather than showing an empty row", () => {
    expect(accountLabel(account({}))).toBe("Account not named in the file")
  })
})

/**
 * Guards the pairing the compiler cannot: that the arrays in `api.ts` and the
 * tables here are the same size. A member added to a copy table but not to the
 * array would go unrendered and untested without this.
 */
describe("vocabulary size", () => {
  it("mirrors the backend enums exactly", () => {
    expect(PRECHECK_OUTCOMES).toHaveLength(7)
    expect(INGEST_OUTCOMES).toHaveLength(12)
    expect(Object.keys(PRECHECK_OUTCOME_VARIANT).sort()).toEqual(
      [...PRECHECK_OUTCOMES].sort()
    )
    expect(Object.keys(INGEST_OUTCOME_VARIANT).sort()).toEqual(
      [...INGEST_OUTCOMES].sort()
    )
  })

  it("keeps the six shared words spelled the same on both sides", () => {
    // The backend maps a precheck outcome across to an ingest one by name in
    // `READING_OUTCOMES`. A rename on one side only would break that mapping
    // silently here, since both are just strings on the wire.
    const shared: readonly (PrecheckOutcome & IngestOutcome)[] = [
      "not_found",
      "unrecognised",
      "ambiguous",
      "out_of_window",
      "unattributable",
      "unreadable",
    ]
    for (const word of shared) {
      expect(PRECHECK_OUTCOMES).toContain(word)
      expect(INGEST_OUTCOMES).toContain(word)
    }
  })
})
