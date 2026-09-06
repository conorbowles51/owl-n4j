/**
 * What the decisions table must never do to a record it is handed.
 *
 * The table fetches nothing, so every case here is a record put in front of it
 * directly. The format module is left real: what is under test is whether this
 * component renders the readings faithfully, and mocking the readers would
 * leave the one thing that can go wrong -- a three-valued answer collapsed into
 * two on the way to the screen -- untested.
 *
 * Three of these are assertions about correctness rather than about markup.
 * A decision this build cannot read must render loudly and must not be reported
 * as having changed nothing. The sentence about order must be drawn by the
 * table itself, so rows cannot appear without it. And a machine writer must be
 * separable at a glance from a person, because the flag exists for exactly that.
 */

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { DecisionRecord } from "../api"
import { DecisionsTable } from "./DecisionsTable"

function makeDecision(overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    id: "dec-1",
    case_id: "case-1",
    subject_type: "transaction",
    subject_id: "txn-9",
    subject_sequence: 1,
    decision: "quarantine_row",
    reason: "Amount disagrees with the statement it was read from.",
    before: { status: "admitted" },
    after: { status: "quarantined" },
    actor_name: "Alex Doyle",
    actor_email: "alex@owlcg.com",
    actor_user_id: "user-1",
    ingestion_run_id: null,
    recorded_at: "2024-03-01T09:15:00Z",
    by_machine: false,
    ...overrides,
  }
}

describe("DecisionsTable with nothing to show", () => {
  it("says there is nothing rather than drawing an empty grid", () => {
    render(<DecisionsTable decisions={[]} />)

    expect(screen.getByTestId("decisions-table-empty").textContent).toContain(
      "No decisions to show."
    )
    expect(screen.queryByTestId("decision-row")).toBeNull()
  })

  /**
   * The caveat belongs to the table and not to its caller, so it is present
   * even here: a caller cannot render rows and omit it, because it has no say.
   */
  it("still carries the sentence about order", () => {
    render(<DecisionsTable decisions={[]} />)

    expect(screen.getByTestId("decision-order-caveat")).toBeTruthy()
  })
})

describe("DecisionsTable drawing records", () => {
  it("draws one row per record, in the order it was handed them", () => {
    render(
      <DecisionsTable
        decisions={[
          makeDecision({ id: "a" }),
          makeDecision({ id: "b" }),
          makeDecision({ id: "c" }),
        ]}
      />
    )

    expect(
      screen
        .getAllByTestId("decision-row")
        .map((row) => row.getAttribute("data-decision-id"))
    ).toEqual(["a", "b", "c"])
  })

  /**
   * Adjacency in this list is not sequence: decisions taken in one act share a
   * timestamp exactly. Nothing may render rows without saying so.
   */
  it("carries the sentence about order alongside the rows", () => {
    render(<DecisionsTable decisions={[makeDecision()]} />)

    const caveat = screen.getByTestId("decision-order-caveat")
    expect(caveat.textContent).toContain("share a time exactly")
    expect(caveat.textContent).toContain("the numbering is the order")
  })

  it("names the decision in words rather than showing the stored term", () => {
    render(<DecisionsTable decisions={[makeDecision()]} />)

    const badge = screen.getByTestId("decision-badge")
    expect(badge.textContent).toContain("Row set aside")
    expect(badge.textContent).not.toContain("quarantine_row")
    expect(badge.getAttribute("data-unrecognised")).toBe("false")
  })

  it("shows the grounds as the person wrote them", () => {
    render(<DecisionsTable decisions={[makeDecision()]} />)

    expect(screen.getByTestId("decision-reason").textContent).toBe(
      "Amount disagrees with the statement it was read from."
    )
  })

  /**
   * A blank cell where the grounds should be reads as no reason having been
   * given, which is a different claim from the entry being incomplete.
   */
  it("names an entry that carries no grounds rather than leaving a gap", () => {
    render(<DecisionsTable decisions={[makeDecision({ reason: "   " })]} />)

    expect(screen.getByTestId("decision-no-reason").textContent).toContain(
      "No grounds recorded"
    )
    expect(screen.queryByTestId("decision-reason")).toBeNull()
  })

  it("names what the decision was about, and which decision about it this is", () => {
    render(
      <DecisionsTable
        decisions={[makeDecision({ subject_type: "source_document", subject_sequence: 3 })]}
      />
    )

    expect(screen.getByTestId("decision-subject").textContent).toBe(
      "Source document"
    )
    expect(screen.getByTestId("decision-subject-id").textContent).toBe("txn-9")
    expect(screen.getByTestId("decision-sequence").textContent).toContain(
      "Decision 3 about this"
    )
  })
})

describe("DecisionsTable and what a decision changed", () => {
  /**
   * `changedStoredState` is three-valued and the screen must keep all three
   * apart. These three cases are the whole reason the effect is rendered as a
   * sentence rather than as a yes or a no.
   */
  it("says a decision that moved something changed what the case reports", () => {
    render(<DecisionsTable decisions={[makeDecision({ decision: "quarantine_row" })]} />)

    const effect = screen.getByTestId("decision-effect")
    expect(effect.getAttribute("data-changed-stored-state")).toBe("true")
    expect(effect.textContent).toContain("changed what the case reports")
  })

  it("says a decision that recorded a view changed nothing about the evidence", () => {
    render(
      <DecisionsTable
        decisions={[makeDecision({ decision: "explain_balance_failure" })]}
      />
    )

    const effect = screen.getByTestId("decision-effect")
    expect(effect.getAttribute("data-changed-stored-state")).toBe("false")
    expect(effect.textContent).toContain("Nothing about the evidence changed")
  })

  /**
   * The one that matters most. An unreadable decision must not be reported as
   * having changed nothing: that is the reassuring answer and it has not been
   * earned. It renders as "cannot tell", and the attribute stays distinct from
   * the false case.
   */
  it("says it cannot tell, for a decision this build does not recognise", () => {
    render(
      <DecisionsTable decisions={[makeDecision({ decision: "seal_under_order" })]} />
    )

    const effect = screen.getByTestId("decision-effect")
    expect(effect.getAttribute("data-changed-stored-state")).toBe("null")
    expect(effect.textContent).toContain("cannot tell")
    expect(effect.textContent).not.toContain("Nothing about the evidence changed")
  })

  it("marks an unrecognised decision loudly, and names the stored word", () => {
    render(
      <DecisionsTable decisions={[makeDecision({ decision: "seal_under_order" })]} />
    )

    const badge = screen.getByTestId("decision-badge")
    expect(badge.getAttribute("data-unrecognised")).toBe("true")
    expect(badge.textContent).toContain("seal_under_order")
  })

  it("marks an unrecognised subject rather than showing a bare stored word", () => {
    render(
      <DecisionsTable decisions={[makeDecision({ subject_type: "custody_chain" })]} />
    )

    const subject = screen.getByTestId("decision-subject")
    expect(subject.getAttribute("data-unrecognised")).toBe("true")
    expect(subject.textContent).toContain("custody_chain")
  })
})

describe("DecisionsTable and who decided", () => {
  it("names the person and keeps their address beside the name", () => {
    render(<DecisionsTable decisions={[makeDecision()]} />)

    const who = screen.getByTestId("decision-decided-by")
    expect(who.textContent).toBe("Alex Doyle")
    expect(who.getAttribute("data-by-machine")).toBe("false")
    expect(screen.getByTestId("decision-decided-by-email").textContent).toBe(
      "alex@owlcg.com"
    )
  })

  /**
   * The stored name on a machine-written entry reads like a person in a column
   * of people. Separating the two at a glance is the entire point of the flag
   * being carried on the record.
   */
  it("shows a machine writer as automatic, not as the name it stored", () => {
    render(
      <DecisionsTable
        decisions={[
          makeDecision({
            by_machine: true,
            actor_name: "reconciliation",
            actor_email: "reconciliation@loupe.invalid",
          }),
        ]}
      />
    )

    const who = screen.getByTestId("decision-decided-by")
    expect(who.textContent).toBe("Automatic")
    expect(who.getAttribute("data-by-machine")).toBe("true")
    expect(screen.queryByTestId("decision-decided-by-email")).toBeNull()
  })

  it("says an entry with neither name nor address is not recorded", () => {
    render(
      <DecisionsTable
        decisions={[makeDecision({ actor_name: "", actor_email: "" })]}
      />
    )

    expect(screen.getByTestId("decision-decided-by").textContent).toBe(
      "Not recorded"
    )
  })
})

describe("DecisionsTable and when", () => {
  it("shows the recorded time", () => {
    render(<DecisionsTable decisions={[makeDecision()]} />)

    expect(screen.getByTestId("decision-recorded-at").textContent).not.toBe("")
  })

  /**
   * A blank time cell reads as an entry with no moment attached, which is a
   * claim about the record rather than about this build's reading of it.
   */
  it("names a missing time rather than leaving the cell blank", () => {
    render(<DecisionsTable decisions={[makeDecision({ recorded_at: null })]} />)

    const cell = screen.getByTestId("decision-recorded-at")
    expect(cell.textContent).not.toBe("")
    expect(cell.textContent).not.toContain("Invalid Date")
  })
})
