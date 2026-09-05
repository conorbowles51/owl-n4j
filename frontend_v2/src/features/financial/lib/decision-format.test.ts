/**
 * Reading a recorded decision for display.
 *
 * Four things here are worth more than the coverage.
 *
 * Two members of the vocabulary read backwards from their own names.
 * `admit_financial_document` sounds like a document entering the ledger and
 * means the opposite, and `explain_balance_failure` sounds like a disposition
 * and moves nothing. Both are pinned to the sense the backend states, so that
 * a later edit tidying up the wording cannot quietly reverse either one.
 *
 * `changedStoredState` is three-valued for the same reason
 * `QuarantineGrounds.decidedByPerson` is, and the test that matters is the
 * null: a decision this build cannot read must not be reported as having
 * changed nothing, which is the reassuring answer and the one it has not
 * earned.
 *
 * `by_machine` is read off the record and never re-derived. The test for that
 * is a record carrying the reconciliation stage's own address with the flag
 * false, which must read as a person, because the backend is the only place
 * that comparison is allowed to be made.
 *
 * `truncated` looks forward only. It is false on the last page even though
 * pages came before it, so a page that claims to be showing all of them on
 * that basis would be wrong every time a reader pages to the end.
 */

import { describe, expect, it } from "vitest"

import {
  ADJUDICATION_DECISIONS,
  ADJUDICATION_SUBJECTS,
  type DecisionRecord,
  type DecisionsResponse,
} from "../api"
import {
  DECISION_ORDER_IS_NOT_SEQUENCE,
  DECISION_SOURCE,
  describeDecisionPage,
  formatDecisionTime,
  readDecidedBy,
  readDecision,
  readDecisionSubject,
} from "./decision-format"
import { formatRunTime } from "./run-format"

function record(overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    id: "decision-1",
    case_id: "case-1",
    subject_type: "transaction",
    subject_id: "txn-1",
    subject_sequence: 1,
    decision: "quarantine_row",
    reason: "Amount could not be read from the statement.",
    before: null,
    after: null,
    actor_name: "Alex Rowe",
    actor_email: "alex@owl.example",
    actor_user_id: null,
    ingestion_run_id: null,
    recorded_at: "2026-03-04T09:15:00+00:00",
    by_machine: false,
    ...overrides,
  }
}

function page(overrides: Partial<DecisionsResponse> = {}): DecisionsResponse {
  return {
    case_id: "case-1",
    decisions: [],
    total: 0,
    limit: 50,
    offset: 0,
    truncated: false,
    ...overrides,
  }
}

describe("readDecisionSubject", () => {
  it("names every kind of thing a decision can be about", () => {
    for (const subject of ADJUDICATION_SUBJECTS) {
      const reading = readDecisionSubject(subject)
      expect(reading.value).toBe(subject)
      expect(reading.label).not.toBe("")
      expect(reading.label).not.toMatch(/unrecognised/i)
      expect(reading.description).not.toBe("")
    }
  })

  it("separates the one subject that is not part of the ledger", () => {
    // A file can be sent away from the financial subsystem before any
    // financial row exists, so this subject names something the ledger has
    // never held. A reader who takes it for a document row would go looking
    // for totals that were never going to be there.
    const file = readDecisionSubject("evidence_file")
    const document = readDecisionSubject("source_document")
    expect(file.label).not.toBe(document.label)
    expect(file.description).not.toBe(document.description)
  })

  it("names a subject it does not recognise rather than blanking it", () => {
    const reading = readDecisionSubject("counterparty")
    expect(reading.value).toBeNull()
    expect(reading.raw).toBe("counterparty")
    expect(reading.label).toContain("counterparty")
    expect(reading.description).toContain("counterparty")
    expect(reading.description).toContain(DECISION_SOURCE)
  })
})

describe("readDecision", () => {
  it("gives every member of the vocabulary words", () => {
    for (const decision of ADJUDICATION_DECISIONS) {
      const reading = readDecision(decision)
      expect(reading.value).toBe(decision)
      expect(reading.label).not.toBe("")
      expect(reading.label).not.toMatch(/unrecognised/i)
      expect(reading.description).not.toBe("")
      expect(reading.effect).not.toBe("")
    }
  })

  it("gives each member its own label", () => {
    // Two members sharing a label would make a screen show the same phrase
    // for two different things that happened, and nothing else on the row
    // distinguishes them.
    const labels = ADJUDICATION_DECISIONS.map((d) => readDecision(d).label)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it("does not spend the unrecognised colour on a member it recognises", () => {
    // `warning` means "this build cannot read this value" everywhere else, and
    // a member wearing it would make a decision that was read perfectly well
    // look like one that was not.
    for (const decision of ADJUDICATION_DECISIONS) {
      expect(readDecision(decision).variant).not.toBe("warning")
    }
  })

  it("says which decisions moved something and which recorded a view", () => {
    // Taken from the vocabulary's own statement of it. These two change no
    // stored column: one explains why an identity does not close and leaves
    // the standing exactly as it was, and the other authorises a send, where
    // held was never a stored state to begin with.
    const recordsAView = ADJUDICATION_DECISIONS.filter(
      (d) => readDecision(d).changedStoredState === false
    )
    expect([...recordsAView].sort()).toEqual([
      "admit_financial_document",
      "explain_balance_failure",
    ])
  })

  it("reserves the irreversible colour for the one decision that is", () => {
    // Every other disposition has a reversal, or changed nothing. A purge is
    // the only one where the subject stops existing.
    const solid = ADJUDICATION_DECISIONS.filter(
      (d) => readDecision(d).variant === "destructive"
    )
    expect(solid).toEqual(["purge_duplicate"])
  })

  it("reads admit_financial_document the way round it actually means", () => {
    // The name points the wrong way: `financial` describes the document, not
    // the destination. It is a bank file the router held back, sent out to
    // text processing by a person, and nothing enters the ledger by it. A
    // reader who took it for an admission would count on totals that will
    // never include those figures.
    const reading = readDecision("admit_financial_document")
    expect(reading.description).toMatch(/nothing was admitted to the ledger/i)
    expect(reading.changedStoredState).toBe(false)
  })

  it("reads explain_balance_failure as a finding and not a disposition", () => {
    // A well-corroborated explanation of a weakly-proved document leaves it
    // weakly proved. Showing it as though it settled something would suggest
    // a document had been cleared when its standing had not moved at all.
    const reading = readDecision("explain_balance_failure")
    expect(reading.description).toMatch(/keeps the standing it had/i)
    expect(reading.effect).toMatch(/nothing about the evidence changed/i)
  })

  it("refuses to guess at a decision it does not recognise", () => {
    const reading = readDecision("withdraw_document")
    expect(reading.value).toBeNull()
    expect(reading.raw).toBe("withdraw_document")
    expect(reading.label).toContain("withdraw_document")
    expect(reading.variant).toBe("warning")
    // Null, not false. False would report an unknown decision as having
    // changed nothing.
    expect(reading.changedStoredState).toBeNull()
    expect(reading.effect).not.toBe("")
  })
})

describe("readDecidedBy", () => {
  it("marks a decision the software took", () => {
    const decided = readDecidedBy(record({ by_machine: true }))
    expect(decided.byMachine).toBe(true)
    expect(decided.label).toBe("Automatic")
    // The reconciliation stage's address is an internal marker at a reserved
    // domain, not somewhere a reply could go.
    expect(decided.email).toBeNull()
    expect(decided.description).not.toBe("")
  })

  it("replaces the machine's stored name rather than showing it", () => {
    // It is stored as a plain string and reads like a person in a column of
    // people. A reader skimming for who acted needs the two kinds separated
    // at a glance.
    const decided = readDecidedBy(
      record({
        by_machine: true,
        actor_name: "Loupe reconciliation stage",
        actor_email: "reconciliation@loupe.invalid",
      })
    )
    expect(decided.label).toBe("Automatic")
    expect(decided.label).not.toContain("Loupe")
  })

  it("never re-derives the flag from the address", () => {
    // The backend makes this comparison once and this module reads the answer.
    // A second implementation here that got it wrong would show software
    // moving a document as though an analyst had, or the reverse, which is the
    // most misleading thing this log could be made to say.
    const decided = readDecidedBy(
      record({
        by_machine: false,
        actor_name: "Loupe reconciliation stage",
        actor_email: "reconciliation@loupe.invalid",
      })
    )
    expect(decided.byMachine).toBe(false)
    expect(decided.label).toBe("Loupe reconciliation stage")
  })

  it("prefers the name, because a name is what a person reads", () => {
    const decided = readDecidedBy(record())
    expect(decided.label).toBe("Alex Rowe")
    // Offered beside it rather than instead of it, so two people with one
    // name stay separable.
    expect(decided.email).toBe("alex@owl.example")
  })

  it("falls back to the address when no name was written down", () => {
    const decided = readDecidedBy(record({ actor_name: "   " }))
    expect(decided.label).toBe("alex@owl.example")
    expect(decided.email).toBe("alex@owl.example")
  })

  it("says an entry is incomplete rather than rendering nobody", () => {
    // Both are copied onto the entry at the time precisely so that who decided
    // survives the account being deleted. An empty space here would read as
    // nobody having decided, which is not a state this log can be in.
    const decided = readDecidedBy(
      record({ actor_name: "", actor_email: "" })
    )
    expect(decided.byMachine).toBe(false)
    expect(decided.label).toBe("Not recorded")
    expect(decided.email).toBeNull()
    expect(decided.description).toMatch(/incomplete/i)
  })
})

describe("formatDecisionTime", () => {
  it("reads a moment the same way a run's timestamps do", () => {
    // Same fixed locale on every machine that opens the case, and the same
    // answer to a value that will not parse. A second implementation would be
    // a second set of answers.
    const stamp = "2026-03-04T09:15:00+00:00"
    expect(formatDecisionTime(stamp)).toBe(formatRunTime(stamp))
    expect(formatDecisionTime(stamp)).not.toMatch(/invalid/i)
  })

  it("names a missing time rather than leaving a blank", () => {
    const text = formatDecisionTime(null)
    expect(text).not.toBe("")
    expect(text).toBe(formatRunTime(null))
  })

  it("shows a value it cannot parse as it arrived", () => {
    expect(formatDecisionTime("not a date")).toBe("not a date")
  })
})

describe("describeDecisionPage", () => {
  it("says plainly when nothing matches", () => {
    expect(describeDecisionPage(page())).toBe("No decisions match this view.")
  })

  it("counts one decision in the singular", () => {
    const text = describeDecisionPage(
      page({ decisions: [record()], total: 1 })
    )
    expect(text).toContain("1 decision.")
    expect(text).not.toContain("1 decisions")
  })

  it("claims to be showing all of them only from the start of the record", () => {
    const text = describeDecisionPage(
      page({ decisions: [record(), record()], total: 2 })
    )
    expect(text).toBe("Showing all 2 decisions.")
  })

  it("does not read the end of the record as the whole of it", () => {
    // `truncated` looks forward only, so it is false here even though fifty
    // decisions came before this page. Claiming "showing all" from that alone
    // would be wrong every time a reader pages to the end.
    const text = describeDecisionPage(
      page({
        decisions: [record(), record()],
        total: 52,
        offset: 50,
        truncated: false,
      })
    )
    expect(text).toBe("Showing 51 to 52 of 52 decisions.")
    expect(text).not.toMatch(/all/i)
    expect(text).not.toMatch(/more come after/i)
  })

  it("says when there is more of the record after this page", () => {
    const text = describeDecisionPage(
      page({
        decisions: [record(), record()],
        total: 52,
        offset: 0,
        limit: 2,
        truncated: true,
      })
    )
    expect(text).toBe("Showing 1 to 2 of 52 decisions. More come after this page.")
  })

  it("does not report an empty page past the end as an empty record", () => {
    // A reader who paged beyond the last one has an empty page in front of
    // them, not an empty log, and the two call for opposite next moves.
    const text = describeDecisionPage(page({ total: 52, offset: 100 }))
    expect(text).toContain("52 decisions")
    expect(text).not.toBe("No decisions match this view.")
  })

  it("counts what matches the filters rather than the whole case", () => {
    // `total` is the count under the same filters, so the sentence describes
    // its own population and can be shown under any set of them.
    const text = describeDecisionPage(
      page({ decisions: [record()], total: 1 })
    )
    expect(text).toContain("1 decision")
  })
})

describe("DECISION_ORDER_IS_NOT_SEQUENCE", () => {
  it("warns that neighbouring entries are not in the order they happened", () => {
    // Decisions taken in one transaction carry the timestamp identically, so
    // a reader inferring order across subjects would be making a claim about
    // who acted first that nothing in the record supports.
    expect(DECISION_ORDER_IS_NOT_SEQUENCE).not.toBe("")
    expect(DECISION_ORDER_IS_NOT_SEQUENCE).toMatch(/order/i)
  })
})
