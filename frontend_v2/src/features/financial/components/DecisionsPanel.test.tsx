/**
 * The four states a decisions table cannot be in the middle of, and the two
 * claims this panel makes about the page it did get.
 *
 * The hook is mocked rather than the network, because what is under test is the
 * panel's reading of a query result, not the query. `DecisionsTable` is left
 * real, so a state that should not reach the table can be shown not to.
 *
 * Two things here are assertions about correctness rather than about markup.
 * A page that came back empty while the record is not empty must not read as
 * "nothing has been decided", because those two call for opposite next moves.
 * And the heading must come from `describeDecisionPage` rather than from the
 * length of the page, because a sentence composed from the row count would say
 * "12 decisions" over the first twelve of two hundred.
 */

import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { DecisionRecord, DecisionsResponse } from "../api"
import { DecisionsPanel } from "./DecisionsPanel"

const useCaseDecisions = vi.hoisted(() => vi.fn())

vi.mock("../hooks/use-case-decisions", () => ({
  useCaseDecisions,
}))

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

/** A settled, successful query result, shaped as the panel reads it. */
function settled(
  decisions: DecisionRecord[],
  page: Partial<DecisionsResponse> = {}
) {
  const data: DecisionsResponse = {
    case_id: "case-1",
    decisions,
    total: decisions.length,
    limit: 100,
    offset: 0,
    truncated: false,
    ...page,
  }
  return { data, isPending: false, isError: false, error: null }
}

beforeEach(() => {
  useCaseDecisions.mockReset()
})

describe("DecisionsPanel states before there are decisions", () => {
  it("asks for a case rather than reading one, when none is chosen", () => {
    useCaseDecisions.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<DecisionsPanel caseId={undefined} />)

    expect(screen.getByTestId("decisions-no-case")).toBeTruthy()
    expect(screen.queryByTestId("decisions-loading")).toBeNull()
    expect(screen.queryByTestId("decisions-table")).toBeNull()
  })

  it("says the read is in flight", () => {
    useCaseDecisions.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<DecisionsPanel caseId="case-1" />)

    expect(screen.getByTestId("decisions-loading").textContent).toContain(
      "Reading the record of decisions"
    )
    expect(screen.queryByTestId("decisions-table")).toBeNull()
  })

  /**
   * A failed read is the one state in which drawing nothing would be a lie: an
   * empty screen where the record should be reads as a case nothing was ever
   * decided about, which is what a person would say to defend a total.
   */
  it("says the record could not be read, and shows the reason", () => {
    useCaseDecisions.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error("case 9f2 is not visible to this account"),
    })

    render(<DecisionsPanel caseId="case-1" />)

    const failure = screen.getByTestId("decisions-error")
    expect(failure.textContent).toContain("could not be read")
    expect(failure.textContent).toContain("nothing here says why anything was")
    expect(failure.textContent).toContain("is not visible to this account")
    expect(screen.queryByTestId("decisions-table")).toBeNull()
  })

  it("still says the read failed when the reason is not an Error", () => {
    useCaseDecisions.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: "gateway timeout",
    })

    render(<DecisionsPanel caseId="case-1" />)

    expect(screen.getByTestId("decisions-error").textContent).toContain(
      "could not be read"
    )
  })
})

describe("DecisionsPanel with an empty record", () => {
  it("says nothing has been decided, and says what that means for the ledger", () => {
    useCaseDecisions.mockReturnValue(settled([]))

    render(<DecisionsPanel caseId="case-1" />)

    expect(
      screen.getByText("Nothing has been decided about this case")
    ).toBeTruthy()
    expect(
      screen.getByText(/Every row the ledger holds is there as it was read/)
    ).toBeTruthy()
    expect(screen.queryByTestId("decisions-table")).toBeNull()
  })
})

describe("DecisionsPanel and the read it asks for", () => {
  /**
   * The key is `["financial-decisions", caseId, null]`. A second argument
   * here, even `{}`, would open a second cache entry and fetch the same page
   * twice, for the reason `IngestionRunsPanel` gives.
   */
  it("asks for the case's decisions with no filters and no window", () => {
    useCaseDecisions.mockReturnValue(settled([]))

    render(<DecisionsPanel caseId="case-1" />)

    expect(useCaseDecisions).toHaveBeenCalledWith("case-1")
  })
})

describe("DecisionsPanel with decisions", () => {
  it("draws the records it was sent", () => {
    useCaseDecisions.mockReturnValue(
      settled([makeDecision({ id: "a" }), makeDecision({ id: "b" })])
    )

    render(<DecisionsPanel caseId="case-1" />)

    expect(screen.getAllByTestId("decision-row")).toHaveLength(2)
  })

  it("says it is showing all of them when the page is the whole record", () => {
    useCaseDecisions.mockReturnValue(settled([makeDecision(), makeDecision({ id: "b" })]))

    render(<DecisionsPanel caseId="case-1" />)

    expect(screen.getByTestId("decisions-summary").textContent).toBe(
      "Showing all 2 decisions."
    )
  })

  /**
   * The heading must not be composed from the row count. A page of two out of
   * two hundred has to say so, or a reader takes the list for the record.
   */
  it("says which part of the record is on screen, and that more follows", () => {
    useCaseDecisions.mockReturnValue(
      settled([makeDecision(), makeDecision({ id: "b" })], {
        total: 200,
        truncated: true,
      })
    )

    render(<DecisionsPanel caseId="case-1" />)

    const summary = screen.getByTestId("decisions-summary").textContent
    expect(summary).toContain("Showing 1 to 2 of 200 decisions.")
    expect(summary).toContain("More come after this page.")
  })

  /**
   * The panel must not warn on a count disagreement the way its siblings do.
   * This endpoint pages by design, so `total` exceeding the page is the
   * ordinary case and a warning would fire on every case with a history.
   */
  it("does not treat a total larger than the page as a fault", () => {
    useCaseDecisions.mockReturnValue(
      settled([makeDecision()], { total: 200, truncated: true })
    )

    render(<DecisionsPanel caseId="case-1" />)

    expect(screen.queryByTestId("decisions-count-disagreement")).toBeNull()
    expect(screen.getAllByTestId("decision-row")).toHaveLength(1)
  })

  /**
   * A page past the end of the record is not an empty record. It must not draw
   * the empty state, because "nothing has been decided" and "you have paged
   * past the decisions there are" call for opposite next moves.
   */
  it("distinguishes a page with nothing on it from a record with nothing in it", () => {
    useCaseDecisions.mockReturnValue(
      settled([], { total: 200, offset: 400, truncated: false })
    )

    render(<DecisionsPanel caseId="case-1" />)

    expect(
      screen.queryByText("Nothing has been decided about this case")
    ).toBeNull()
    const summary = screen.getByTestId("decisions-summary").textContent
    expect(summary).toContain("Nothing on this page")
    expect(summary).toContain("200 decisions match this view")
  })

  it("carries the sentence about order, drawn by the table", () => {
    useCaseDecisions.mockReturnValue(settled([makeDecision()]))

    render(<DecisionsPanel caseId="case-1" />)

    expect(screen.getByTestId("decision-order-caveat").textContent).toContain(
      "share a time exactly"
    )
  })
})
