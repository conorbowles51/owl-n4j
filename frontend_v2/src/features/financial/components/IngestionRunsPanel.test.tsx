/**
 * The four states an attempts table cannot be in the middle of, and the two
 * claims this panel makes about the attempts it did get.
 *
 * The hook is mocked rather than the network, because what is under test is the
 * panel's reading of a query result, not the query. `IngestionRunsTable` is left
 * real, so a state that should not reach the table can be shown not to.
 *
 * Two things here are assertions about correctness rather than about markup.
 * The panel must not narrow the read to the attempts that finished, because the
 * failures are the whole point of the screen; that is asserted by handing it a
 * mixed list and counting what comes out. And it must call the hook with the
 * case id alone, because a second argument opens a second cache entry and a
 * second request for data `IngestionRunNotice` has already fetched.
 */

import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { IngestionRun, IngestionRunsResponse } from "../api"
import { IngestionRunsPanel } from "./IngestionRunsPanel"

const useIngestionRuns = vi.hoisted(() => vi.fn())

vi.mock("../hooks/use-ingestion-runs", () => ({
  useIngestionRuns,
}))

function makeRun(overrides: Partial<IngestionRun> = {}): IngestionRun {
  return {
    key: "run-1",
    case_id: "case-1",
    status: "completed",
    code_version: "abc123",
    ruleset_version: "2024-03",
    config: {},
    started_by_user_id: "user-1",
    started_by_email: "alex@owlcg.com",
    started_at: "2024-03-01T09:15:00Z",
    completed_at: "2024-03-01T09:17:30Z",
    documents_seen: 3,
    transactions_admitted: 120,
    transactions_quarantined: 4,
    error: null,
    notes: null,
    ...overrides,
  }
}

/** A settled, successful query result, shaped as the panel reads it. */
function settled(runs: IngestionRun[], total?: number) {
  const data: IngestionRunsResponse = {
    case_id: "case-1",
    runs,
    total: total ?? runs.length,
  }
  return { data, isPending: false, isError: false, error: null }
}

beforeEach(() => {
  useIngestionRuns.mockReset()
})

describe("IngestionRunsPanel states before there are attempts", () => {
  it("asks for a case rather than reading one, when none is chosen", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<IngestionRunsPanel caseId={undefined} />)

    expect(screen.getByTestId("runs-no-case")).toBeTruthy()
    expect(screen.queryByTestId("runs-loading")).toBeNull()
    expect(screen.queryByTestId("runs-table")).toBeNull()
  })

  it("says the read is in flight", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.getByTestId("runs-loading").textContent).toContain(
      "Reading the record of past attempts"
    )
    expect(screen.queryByTestId("runs-table")).toBeNull()
  })

  /**
   * A failed read is the one state in which drawing nothing would be a lie: an
   * empty screen where the history should be reads as a case nothing was ever
   * loaded into.
   */
  it("says the record could not be read, and shows the reason", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error("case 9f2 is not visible to this account"),
    })

    render(<IngestionRunsPanel caseId="case-1" />)

    const failure = screen.getByTestId("runs-error")
    expect(failure.textContent).toContain("could not be read")
    expect(failure.textContent).toContain(
      "nothing here says what the ledger was built from"
    )
    expect(failure.textContent).toContain("is not visible to this account")
    expect(screen.queryByTestId("runs-table")).toBeNull()
  })

  it("still says the read failed when the reason is not an Error", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: "gateway timeout",
    })

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.getByTestId("runs-error").textContent).toContain(
      "could not be read"
    )
  })
})

describe("IngestionRunsPanel with no attempts returned", () => {
  /**
   * No recorded attempt is a fact about this record and nothing else. The empty
   * state may not imply the ledger is empty, and may not imply it is full.
   */
  it("says only what this screen holds, claiming nothing about the ledger", () => {
    useIngestionRuns.mockReturnValue(settled([]))

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.getByText("No attempts recorded against this case")).toBeTruthy()
    const description = screen.getByText(/If the ledger holds rows/)
    expect(description.textContent).toContain(
      "this screen has no record of what put them there"
    )
    expect(screen.queryByTestId("runs-table")).toBeNull()
  })
})

describe("IngestionRunsPanel and the read it asks for", () => {
  /**
   * The cache entry `["financial-runs", caseId, null]` is shared with
   * `IngestionRunNotice`, which also calls the hook with the case id alone. A
   * second argument here, even `{}`, would open a second entry and fetch the
   * same data twice.
   */
  it("asks for every attempt on the case, with no window and no status filter", () => {
    useIngestionRuns.mockReturnValue(settled([]))

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(useIngestionRuns).toHaveBeenCalledWith("case-1")
  })
})

describe("IngestionRunsPanel with attempts", () => {
  it("counts the attempts it was sent and renders them", () => {
    useIngestionRuns.mockReturnValue(
      settled([makeRun({ key: "a" }), makeRun({ key: "b" })])
    )

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.getByTestId("runs-summary").textContent).toBe(
      "2 attempts, newest first."
    )
    expect(screen.getAllByTestId("run-row")).toHaveLength(2)
  })

  it("counts one attempt without calling it attempts", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun()]))

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.getByTestId("runs-summary").textContent).toBe(
      "1 attempt, newest first."
    )
  })

  /**
   * The read must not be narrowed to the attempts that broke, nor to the ones
   * that worked. A list filtered either way would answer a different question
   * from the one the screen appears to answer.
   */
  it("draws the attempts that finished alongside the ones that did not", () => {
    useIngestionRuns.mockReturnValue(
      settled([
        makeRun({ key: "done", status: "completed" }),
        makeRun({ key: "broke", status: "failed" }),
        makeRun({ key: "open", status: "running", completed_at: null }),
      ])
    )

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(
      screen.getAllByTestId("run-row").map((r) => r.getAttribute("data-run-key"))
    ).toEqual(["done", "broke", "open"])
  })

  it("stays quiet when the reported total and the attempts sent agree", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun()], 1))

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.queryByTestId("runs-count-disagreement")).toBeNull()
  })

  /**
   * The endpoint returns `total` as the length of the same list, so the two can
   * only differ if the backend has started paging without this screen knowing,
   * at which point a history that looks complete is a window onto part of one.
   */
  it("says so when the reported total and the attempts sent disagree", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun()], 40))

    render(<IngestionRunsPanel caseId="case-1" />)

    const warning = screen.getByTestId("runs-count-disagreement")
    expect(warning.textContent).toContain("reported 40 attempts and sent 1")
    expect(warning.textContent).toContain("not all of it")
    expect(screen.getAllByTestId("run-row")).toHaveLength(1)
  })

  it("carries the sentence that qualifies the counts", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun()]))

    render(<IngestionRunsPanel caseId="case-1" />)

    expect(screen.getByTestId("run-counts-are-history").textContent).toContain(
      "a record of the attempt"
    )
  })
})
