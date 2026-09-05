/**
 * Reading the answer to an attempt to change a ledger row's standing.
 *
 * These tests guard three things, and all three are about not saying something
 * untrue on a screen that sits over an evidence log.
 *
 * **A refusal is an answer, not a failure.** Four of the six outcomes wrote
 * nothing, and only two of those four are anything to be alarmed about. So the
 * tests check that every outcome is named and described, and that the two that
 * moved the row are the only two `changedTheRow` is true of.
 *
 * **Nothing in this answer is the words the person typed.** `reason` carries
 * four different things depending on the outcome and none of them is what was
 * written in the box. The tests hold the mapping from outcome to meaning, so a
 * later edit cannot quietly start presenting the system's own note as somebody's
 * stated grounds.
 *
 * **`rescues_period` has three values and they are not two.** `false` and
 * `null` must not render alike, and a fourth presentation exists for the case
 * where the question never arose at all. The tests assert all four are
 * distinct and none is blank, because the only way a caller can collapse them
 * is if this module hands back something collapsible.
 */

import { describe, expect, it } from "vitest"

import { ROW_ADJUDICATION_OUTCOMES, type RowAdjudication } from "../api"
import {
  ADJUDICATION_REASON_IS_NEVER_THE_PERSONS,
  ADJUDICATION_SOURCE,
  readAdjudicationReason,
  readRescueOutcome,
  readRowAdjudication,
  readRowAdjudicationOutcome,
} from "./adjudication-format"

function answer(overrides: Partial<RowAdjudication> = {}): RowAdjudication {
  return {
    transaction_id: "txn-1",
    outcome: "quarantined",
    applied: true,
    reason: null,
    ledger_status: "quarantined",
    quarantine_reason: "adjudicated",
    adjudication_id: "adj-1",
    rescues_period: false,
    ...overrides,
  }
}

describe("readRowAdjudicationOutcome", () => {
  it("names every outcome the backend can return", () => {
    for (const outcome of ROW_ADJUDICATION_OUTCOMES) {
      const reading = readRowAdjudicationOutcome(outcome)
      expect(reading.value).toBe(outcome)
      expect(reading.label).not.toBe("")
      expect(reading.label).not.toMatch(/unrecognised/i)
      expect(reading.description).not.toBe("")
    }
  })

  it("gives every outcome its own label", () => {
    const labels = ROW_ADJUDICATION_OUTCOMES.map(
      (outcome) => readRowAdjudicationOutcome(outcome).label
    )
    expect(new Set(labels).size).toBe(ROW_ADJUDICATION_OUTCOMES.length)
  })

  it("says the row moved for exactly the two outcomes that wrote", () => {
    expect(readRowAdjudicationOutcome("quarantined").changedTheRow).toBe(true)
    expect(readRowAdjudicationOutcome("released").changedTheRow).toBe(true)
    expect(readRowAdjudicationOutcome("unchanged").changedTheRow).toBe(false)
    expect(readRowAdjudicationOutcome("refused").changedTheRow).toBe(false)
    expect(readRowAdjudicationOutcome("not_found").changedTheRow).toBe(false)
    expect(readRowAdjudicationOutcome("write_failed").changedTheRow).toBe(false)
  })

  it("will not guess either way about a word it cannot read", () => {
    // Guessing false hides a change that happened; guessing true claims one
    // that may not have. Neither is available.
    expect(readRowAdjudicationOutcome("withdrawn").changedTheRow).toBeNull()
  })

  it("names an unrecognised outcome rather than rendering it blank", () => {
    const reading = readRowAdjudicationOutcome("withdrawn")
    expect(reading.value).toBeNull()
    expect(reading.raw).toBe("withdrawn")
    expect(reading.label).toContain("withdrawn")
    expect(reading.description).not.toBe("")
  })

  it("says an unreadable outcome came from the write, not from the ledger", () => {
    // An outcome is never stored, so "it came from the ledger" would be false
    // and would send a reader looking for a row that says this.
    const reading = readRowAdjudicationOutcome("withdrawn")
    expect(reading.description).toContain(ADJUDICATION_SOURCE)
    expect(reading.description).not.toContain("came from the ledger")
  })

  it("keeps the colour reserved for unreadable values off every known outcome", () => {
    const unrecognised = readRowAdjudicationOutcome("withdrawn").variant
    for (const outcome of ROW_ADJUDICATION_OUTCOMES) {
      expect(readRowAdjudicationOutcome(outcome).variant).not.toBe(unrecognised)
    }
  })

  it("badges a set-aside row the colour the ledger table badges it", () => {
    expect(readRowAdjudicationOutcome("quarantined").variant).toBe("amber")
    expect(readRowAdjudicationOutcome("released").variant).toBe("success")
  })
})

describe("readRescueOutcome", () => {
  it("keeps all four readings distinct and none of them blank", () => {
    const readings = [
      readRescueOutcome(answer({ rescues_period: true })),
      readRescueOutcome(answer({ rescues_period: false })),
      readRescueOutcome(answer({ rescues_period: null })),
      readRescueOutcome(
        answer({ outcome: "released", rescues_period: null, applied: true })
      ),
    ]
    for (const reading of readings) {
      expect(reading.label).not.toBe("")
      expect(reading.description).not.toBe("")
    }
    expect(new Set(readings.map((r) => r.key)).size).toBe(4)
    expect(new Set(readings.map((r) => r.label)).size).toBe(4)
  })

  it("does not render no and unknown alike", () => {
    // The whole reason this reader exists. "No statement balanced by this" and
    // "the question could not be answered" are different facts about a case.
    const no = readRescueOutcome(answer({ rescues_period: false }))
    const unknown = readRescueOutcome(answer({ rescues_period: null }))
    expect(no.key).toBe("rescue-none")
    expect(unknown.key).toBe("rescue-unknown")
    expect(no.label).not.toBe(unknown.label)
    expect(no.description).not.toBe(unknown.description)
  })

  it("says the statement balances when the backend said so", () => {
    const reading = readRescueOutcome(answer({ rescues_period: true }))
    expect(reading.key).toBe("rescue-balanced")
    expect(reading.raw).toBe(true)
  })

  it("does not let a balanced statement read as grounds on its own", () => {
    // Taking out the row that was the gap always closes the gap, so this is
    // arithmetic. The copy has to say that where the reader will see it.
    const reading = readRescueOutcome(answer({ rescues_period: true }))
    expect(reading.description).toMatch(/arithmetic/i)
  })

  it("says the question was never asked where nothing came out of the ledger", () => {
    for (const outcome of ["released", "unchanged", "refused", "not_found", "write_failed"]) {
      const reading = readRescueOutcome(answer({ outcome, rescues_period: null }))
      expect(reading.key).toBe("rescue-not-asked")
    }
  })

  it("takes a positive answer at face value whatever the outcome says", () => {
    // The backend asserted something. This build does not know better than an
    // assertion it did not make.
    const reading = readRescueOutcome(answer({ outcome: "refused", rescues_period: true }))
    expect(reading.key).toBe("rescue-balanced")
  })

  it("claims nothing about a quarantine whose outcome word it cannot read", () => {
    const reading = readRescueOutcome(answer({ outcome: "withdrawn", rescues_period: null }))
    expect(reading.key).toBe("rescue-unknown")
    expect(reading.raw).toBeNull()
  })

  it("carries the value it was given so a caller can show the distinction", () => {
    expect(readRescueOutcome(answer({ rescues_period: true })).raw).toBe(true)
    expect(readRescueOutcome(answer({ rescues_period: false })).raw).toBe(false)
    expect(readRescueOutcome(answer({ rescues_period: null })).raw).toBeNull()
  })
})

describe("readAdjudicationReason", () => {
  it("reads the field's meaning off the outcome and nowhere else", () => {
    // The same sentence means different things under different outcomes, and
    // the text itself gives no clue which.
    const text = "Something the backend wrote."
    expect(readAdjudicationReason(answer({ outcome: "quarantined", reason: text })).kind).toBe(
      "rescue-note"
    )
    expect(readAdjudicationReason(answer({ outcome: "refused", reason: text })).kind).toBe(
      "why-refused"
    )
    expect(readAdjudicationReason(answer({ outcome: "unchanged", reason: text })).kind).toBe(
      "why-unchanged"
    )
    expect(readAdjudicationReason(answer({ outcome: "released", reason: text })).kind).toBe(
      "not-carried"
    )
  })

  it("flags an outcome that should have left as an HTTP error", () => {
    // The router turns both of these into 404 and 500, so a body carrying one
    // means something upstream changed. Shown, not swallowed.
    expect(readAdjudicationReason(answer({ outcome: "not_found" })).kind).toBe("unexpected")
    expect(readAdjudicationReason(answer({ outcome: "write_failed" })).kind).toBe("unexpected")
  })

  it("refuses to attribute text arriving under a word it cannot read", () => {
    const reading = readAdjudicationReason(
      answer({ outcome: "withdrawn", reason: "Something happened." })
    )
    expect(reading.kind).toBe("unattributed")
    expect(reading.text).toBe("Something happened.")
  })

  it("always has a heading, so text cannot be rendered with nothing over it", () => {
    for (const outcome of [...ROW_ADJUDICATION_OUTCOMES, "withdrawn"]) {
      const reading = readAdjudicationReason(answer({ outcome, reason: "text" }))
      expect(reading.heading).not.toBe("")
    }
  })

  it("gives each meaning its own heading", () => {
    const headings = [...ROW_ADJUDICATION_OUTCOMES, "withdrawn"].map(
      (outcome) => readAdjudicationReason(answer({ outcome })).heading
    )
    // Six outcomes plus an unreadable word, but not_found and write_failed
    // share the one meaning, so six distinct headings and not seven.
    expect(new Set(headings).size).toBe(6)
  })

  it("carries no text where the field is empty or blank", () => {
    expect(readAdjudicationReason(answer({ outcome: "released", reason: null })).text).toBeNull()
    expect(readAdjudicationReason(answer({ reason: "   " })).text).toBeNull()
  })

  it("passes the backend's wording through without editing it", () => {
    const text = "Statement 4402 balances once this row is out."
    expect(readAdjudicationReason(answer({ reason: text })).text).toBe(text)
  })
})

describe("ADJUDICATION_REASON_IS_NEVER_THE_PERSONS", () => {
  it("tells the reader the wording is the system's and theirs is on the record", () => {
    // Held as one string so the screen and this test cannot drift, the way
    // RUN_COUNTS_ARE_HISTORY is on a run.
    expect(ADJUDICATION_REASON_IS_NEVER_THE_PERSONS).toMatch(/not yours/)
    expect(ADJUDICATION_REASON_IS_NEVER_THE_PERSONS).toMatch(/record/)
  })
})

describe("readRowAdjudication", () => {
  it("reads a quarantine whole", () => {
    const reading = readRowAdjudication(
      answer({
        outcome: "quarantined",
        applied: true,
        reason: "Statement 4402 balances once this row is out.",
        rescues_period: true,
      })
    )
    expect(reading.transactionId).toBe("txn-1")
    expect(reading.outcome.value).toBe("quarantined")
    expect(reading.applied).toBe(true)
    expect(reading.appliedDisagreesWithOutcome).toBe(false)
    expect(reading.reason.kind).toBe("rescue-note")
    expect(reading.rescue.key).toBe("rescue-balanced")
    expect(reading.ledgerStatus?.value).toBe("quarantined")
    expect(reading.quarantineReason?.value).toBe("adjudicated")
    expect(reading.adjudicationId).toBe("adj-1")
  })

  it("reads a release, whose row keeps no trace of having been held", () => {
    // The database's own rule nulls the grounds on release, so on the row
    // alone a released row and one never set aside are the same thing.
    const reading = readRowAdjudication(
      answer({
        outcome: "released",
        applied: true,
        reason: null,
        ledger_status: "admitted",
        quarantine_reason: null,
        rescues_period: null,
      })
    )
    expect(reading.quarantineReason).toBeNull()
    expect(reading.reason.kind).toBe("not-carried")
    expect(reading.reason.text).toBeNull()
    expect(reading.rescue.key).toBe("rescue-not-asked")
  })

  it("reports a wire that contradicts its own outcome", () => {
    // applied and outcome are derived from each other on the backend and
    // cannot disagree there. A disagreement means the two builds do not mean
    // the same thing by a word, which has to be visible.
    const hidden = readRowAdjudication(answer({ outcome: "quarantined", applied: false }))
    expect(hidden.appliedDisagreesWithOutcome).toBe(true)

    const claimed = readRowAdjudication(answer({ outcome: "refused", applied: true }))
    expect(claimed.appliedDisagreesWithOutcome).toBe(true)
  })

  it("reports no contradiction when the outcome word cannot be read", () => {
    // There is nothing to compare against, so there is nothing to report.
    const reading = readRowAdjudication(answer({ outcome: "withdrawn", applied: true }))
    expect(reading.outcome.changedTheRow).toBeNull()
    expect(reading.appliedDisagreesWithOutcome).toBe(false)
  })

  it("leaves the ledger's own words to the ledger's own readers", () => {
    // ledger_status and quarantine_reason are copied straight off the stored
    // row, so they are narrowed as ledger values and say so when unreadable.
    const reading = readRowAdjudication(answer({ ledger_status: "sealed" }))
    expect(reading.ledgerStatus?.value).toBeNull()
    expect(reading.ledgerStatus?.raw).toBe("sealed")
    expect(reading.ledgerStatus?.description).toContain("came from the ledger")
  })

  it("gives no status where the answer carried none", () => {
    const reading = readRowAdjudication(
      answer({
        outcome: "not_found",
        applied: false,
        ledger_status: null,
        quarantine_reason: null,
        adjudication_id: null,
        rescues_period: null,
      })
    )
    expect(reading.ledgerStatus).toBeNull()
    expect(reading.quarantineReason).toBeNull()
    expect(reading.adjudicationId).toBeNull()
  })

  it("claims no decision for an outcome that appended none", () => {
    // unchanged means somebody else's earlier decision holds this row. This
    // attempt did not make it, so no id is claimed for it.
    const reading = readRowAdjudication(
      answer({
        outcome: "unchanged",
        applied: false,
        reason: "This row was already set aside by a person.",
        adjudication_id: null,
        rescues_period: null,
      })
    )
    expect(reading.adjudicationId).toBeNull()
    expect(reading.reason.kind).toBe("why-unchanged")
    expect(reading.reason.text).not.toBeNull()
  })
})
