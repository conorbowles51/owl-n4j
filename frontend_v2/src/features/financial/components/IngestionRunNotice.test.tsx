/**
 * What the notice says, and the four states in which it says nothing.
 *
 * Silence is most of this file. A component whose normal output is nothing at
 * all can be broken in two directions, and the expensive direction is the quiet
 * one: a notice that fails to appear leaves a short ledger looking complete.
 * So the cases that should render nothing are asserted as carefully as the
 * cases that should render something, and each one names why it is silent.
 *
 * The hook is mocked rather than the network, because what is under test is the
 * component's reading of a query result. `Badge` and the formatters are left
 * real, so the words on screen are the ones the formatters actually produce.
 */

import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { IngestionRun, IngestionRunsResponse } from "../api"
import { IngestionRunNotice } from "./IngestionRunNotice"

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

/** A settled, successful query result, shaped as the component reads it. */
function settled(runs: IngestionRun[]) {
  const data: IngestionRunsResponse = {
    case_id: "case-1",
    runs,
    total: runs.length,
  }
  return { data, isPending: false, isError: false, error: null }
}

beforeEach(() => {
  useIngestionRuns.mockReset()
})

describe("IngestionRunNotice when it has nothing to say", () => {
  it("says nothing with no case chosen, rather than reporting on no case", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    const { container } = render(<IngestionRunNotice caseId={undefined} />)

    expect(container.textContent).toBe("")
  })

  it("says nothing while the read is in flight, having nothing to report yet", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    const { container } = render(<IngestionRunNotice caseId="case-1" />)

    expect(container.textContent).toBe("")
  })

  it("says nothing when every attempt finished", () => {
    useIngestionRuns.mockReturnValue(
      settled([makeRun({ key: "a" }), makeRun({ key: "b" })])
    )

    const { container } = render(<IngestionRunNotice caseId="case-1" />)

    expect(container.textContent).toBe("")
    expect(screen.queryByTestId("run-notice")).toBeNull()
  })

  it("says nothing when the case has no attempts recorded at all", () => {
    useIngestionRuns.mockReturnValue(settled([]))

    const { container } = render(<IngestionRunNotice caseId="case-1" />)

    expect(container.textContent).toBe("")
  })

  it("raises no alarm about a status this build does not recognise", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun({ status: "superseded" })]))

    const { container } = render(<IngestionRunNotice caseId="case-1" />)

    expect(container.textContent).toBe("")
  })
})

describe("IngestionRunNotice when the attempts cannot be read", () => {
  it("says the record could not be read, rather than rendering silence", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error("case 9f2 is not visible to this account"),
    })

    render(<IngestionRunNotice caseId="case-1" />)

    const failure = screen.getByTestId("run-notice-read-failed")
    expect(failure.textContent).toContain("could not be read")
    expect(failure.textContent).toContain(
      "nothing here says whether everything sent to it arrived"
    )
    expect(failure.textContent).toContain("is not visible to this account")
    expect(screen.queryByTestId("run-notice")).toBeNull()
  })

  it("still says the read failed when the reason is not an Error", () => {
    useIngestionRuns.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: "gateway timeout",
    })

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.getByTestId("run-notice-read-failed").textContent).toContain(
      "could not be read"
    )
  })
})

describe("IngestionRunNotice on an attempt that did not finish", () => {
  it("says one attempt did not finish, in the singular", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun({ status: "failed" })]))

    render(<IngestionRunNotice caseId="case-1" />)

    const headline = screen.getByTestId("run-notice-headline")
    expect(headline.textContent).toContain(
      "One attempt to load evidence into this ledger has not finished."
    )
    expect(headline.textContent).toContain("less than the evidence it was given")
    expect(screen.getAllByTestId("run-notice-item")).toHaveLength(1)
  })

  it("counts the attempts and switches to the plural", () => {
    useIngestionRuns.mockReturnValue(
      settled([
        makeRun({ key: "a", status: "failed" }),
        makeRun({ key: "b", status: "aborted" }),
        makeRun({ key: "c", status: "running" }),
      ])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    const headline = screen.getByTestId("run-notice-headline")
    expect(headline.textContent).toContain(
      "3 attempts to load evidence into this ledger have not finished."
    )
    expect(headline.textContent).toContain("less than the evidence they were given")
    expect(screen.getAllByTestId("run-notice-item")).toHaveLength(3)
  })

  it("passes over the attempts that finished and keeps only the rest", () => {
    useIngestionRuns.mockReturnValue(
      settled([
        makeRun({ key: "done", status: "completed" }),
        makeRun({ key: "broke", status: "failed" }),
        makeRun({ key: "also-done", status: "completed" }),
      ])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    const items = screen.getAllByTestId("run-notice-item")
    expect(items).toHaveLength(1)
    expect(items[0].getAttribute("data-run-key")).toBe("broke")
  })

  it("is not truncated, however many attempts broke", () => {
    useIngestionRuns.mockReturnValue(
      settled(
        Array.from({ length: 6 }, (_unused, index) =>
          makeRun({ key: `run-${index}`, status: "failed" })
        )
      )
    )

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.getAllByTestId("run-notice-item")).toHaveLength(6)
  })
})

describe("IngestionRunNotice on what each flagged attempt says", () => {
  it("names the status and what it means for the ledger", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun({ status: "failed" })]))

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.getByTestId("run-notice-status").textContent).toBe("Broke")
    expect(screen.getByTestId("run-notice-description").textContent).toContain(
      "stopped part way"
    )
  })

  it("reports when an open attempt started and claims nothing more about it", () => {
    useIngestionRuns.mockReturnValue(
      settled([makeRun({ status: "running", completed_at: null })])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.getByTestId("run-notice-status").textContent).toBe("In progress")
    expect(screen.getByTestId("run-notice-detail").textContent).toContain(
      "Started 01 Mar 2024, 09:15 by alex@owlcg.com"
    )
    expect(screen.getByTestId("run-notice-description").textContent).toContain(
      "not final until it ends"
    )
  })

  it("falls back to the user id, then to a stated absence, for who started it", () => {
    useIngestionRuns.mockReturnValue(
      settled([
        makeRun({
          key: "no-email",
          status: "failed",
          started_by_email: null,
          started_by_user_id: "user-7",
        }),
        makeRun({
          key: "no-one",
          status: "failed",
          started_by_email: null,
          started_by_user_id: null,
        }),
      ])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    const details = screen.getAllByTestId("run-notice-detail")
    expect(details[0].textContent).toContain("by User user-7")
    expect(details[1].textContent).toContain("by Not recorded")
  })

  it("says the start time was not recorded rather than leaving a gap", () => {
    useIngestionRuns.mockReturnValue(
      settled([makeRun({ status: "pending", started_at: null })])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.getByTestId("run-notice-detail").textContent).toContain(
      "Started Not recorded"
    )
  })

  it("shows what broke the attempt, when the attempt recorded it", () => {
    useIngestionRuns.mockReturnValue(
      settled([
        makeRun({
          status: "failed",
          error: "PdfReadError: EOF marker not found",
        }),
      ])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.getByTestId("run-notice-error-text").textContent).toBe(
      "PdfReadError: EOF marker not found"
    )
  })

  it("shows no error line when the attempt recorded none", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun({ status: "aborted" })]))

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.queryByTestId("run-notice-error-text")).toBeNull()
  })

  it("shows no error line for an empty error string either", () => {
    useIngestionRuns.mockReturnValue(settled([makeRun({ status: "failed", error: "" })]))

    render(<IngestionRunNotice caseId="case-1" />)

    expect(screen.queryByTestId("run-notice-error-text")).toBeNull()
  })

  it("carries no counts, which would read as counts of the ledger", () => {
    useIngestionRuns.mockReturnValue(
      settled([
        makeRun({
          status: "failed",
          documents_seen: 9,
          transactions_admitted: 812,
          transactions_quarantined: 37,
        }),
      ])
    )

    render(<IngestionRunNotice caseId="case-1" />)

    const notice = screen.getByTestId("run-notice")
    expect(notice.textContent).not.toContain("812")
    expect(notice.textContent).not.toContain("37")
  })
})

describe("IngestionRunNotice and the read it asks for", () => {
  it("asks for every attempt on the case, with no window and no status filter", () => {
    useIngestionRuns.mockReturnValue(settled([]))

    render(<IngestionRunNotice caseId="case-1" />)

    expect(useIngestionRuns).toHaveBeenCalledWith("case-1")
  })
})
