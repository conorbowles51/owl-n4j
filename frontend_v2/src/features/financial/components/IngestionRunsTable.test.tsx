/**
 * What the attempts table has to get right about a run it is handed.
 *
 * The expensive failures here are the quiet ones. A count shown without the
 * sentence that qualifies it reads as a count of the ledger. A blank duration
 * reads as an attempt that took no time. A dropped row reads as an attempt that
 * never happened. Each of those is asserted directly rather than inferred from
 * the shape of the markup.
 *
 * Nothing is mocked: the component fetches nothing, and the formatters are left
 * real so the words asserted here are the words a reader sees.
 */

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { IngestionRun } from "../api"
import { RUN_COUNTS_ARE_HISTORY } from "../lib/run-format"
import { IngestionRunsTable } from "./IngestionRunsTable"

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

describe("IngestionRunsTable, the history it draws", () => {
  it("draws every attempt it is handed, the ones that finished included", () => {
    render(
      <IngestionRunsTable
        runs={[
          makeRun({ key: "a", status: "completed" }),
          makeRun({ key: "b", status: "failed" }),
          makeRun({ key: "c", status: "aborted" }),
        ]}
      />
    )

    const rows = screen.getAllByTestId("run-row")
    expect(rows).toHaveLength(3)
    expect(rows.map((r) => r.getAttribute("data-run-key"))).toEqual(["a", "b", "c"])
  })

  it("keeps the order it was given, the backend having already ordered them", () => {
    render(
      <IngestionRunsTable
        runs={[
          makeRun({ key: "newest", started_at: "2024-03-03T09:00:00Z" }),
          makeRun({ key: "oldest", started_at: "2024-01-01T09:00:00Z" }),
          makeRun({ key: "middle", started_at: "2024-02-01T09:00:00Z" }),
        ]}
      />
    )

    expect(
      screen.getAllByTestId("run-row").map((r) => r.getAttribute("data-run-key"))
    ).toEqual(["newest", "oldest", "middle"])
  })

  it("says there is nothing to show rather than drawing a header over nothing", () => {
    render(<IngestionRunsTable runs={[]} />)

    expect(screen.getByTestId("runs-table-empty")).toBeInTheDocument()
    expect(screen.queryAllByTestId("run-row")).toHaveLength(0)
  })
})

describe("IngestionRunsTable, the counts", () => {
  it("shows the three figures the attempt recorded", () => {
    render(
      <IngestionRunsTable
        runs={[
          makeRun({ documents_seen: 7, transactions_admitted: 913, transactions_quarantined: 22 }),
        ]}
      />
    )

    expect(screen.getByTestId("run-documents-seen")).toHaveTextContent("7")
    expect(screen.getByTestId("run-admitted")).toHaveTextContent("913")
    expect(screen.getByTestId("run-quarantined")).toHaveTextContent("22")
  })

  /**
   * The whole reason the counts live on this screen rather than in the notice
   * above the ledger. Without the sentence they read as a count of the ledger
   * as it stands, which they are not.
   */
  it("never draws the counts without saying they are a record of the attempt", () => {
    render(<IngestionRunsTable runs={[makeRun()]} />)

    expect(screen.getByTestId("run-counts-are-history")).toHaveTextContent(
      RUN_COUNTS_ARE_HISTORY
    )
  })

  it("shows a zero as a zero, a run having genuinely taken nothing in", () => {
    render(
      <IngestionRunsTable
        runs={[
          makeRun({
            status: "failed",
            documents_seen: 0,
            transactions_admitted: 0,
            transactions_quarantined: 0,
          }),
        ]}
      />
    )

    expect(screen.getByTestId("run-documents-seen")).toHaveTextContent("0")
    expect(screen.getByTestId("run-admitted")).toHaveTextContent("0")
  })
})

describe("IngestionRunsTable, a status this build cannot read", () => {
  it("shows the row and names the value rather than dropping either", () => {
    render(<IngestionRunsTable runs={[makeRun({ status: "reconciling" })]} />)

    expect(screen.getAllByTestId("run-row")).toHaveLength(1)
    expect(screen.getByTestId("run-status")).toHaveTextContent("Unrecognised (reconciling)")
  })

  /**
   * The notice stays quiet on an unknown status because it is a warning. A list
   * of everything cannot: a row it could not read has to look different from a
   * row it could.
   */
  it("marks it as unread and gives it the variant reserved for that", () => {
    render(<IngestionRunsTable runs={[makeRun({ status: "reconciling" })]} />)

    const badge = screen.getByTestId("run-status")
    expect(badge).toHaveAttribute("data-unrecognised", "true")
    expect(badge).toHaveAttribute("data-variant", "warning")
  })

  it("marks a status it does recognise as recognised", () => {
    render(<IngestionRunsTable runs={[makeRun({ status: "completed" })]} />)

    const badge = screen.getByTestId("run-status")
    expect(badge).toHaveAttribute("data-unrecognised", "false")
    expect(badge).toHaveTextContent("Finished")
  })
})

describe("IngestionRunsTable, when an attempt started and ended", () => {
  it("shows both times and how long it took", () => {
    render(
      <IngestionRunsTable
        runs={[
          makeRun({
            started_at: "2024-03-01T09:15:00Z",
            completed_at: "2024-03-01T09:17:30Z",
          }),
        ]}
      />
    )

    expect(screen.getByTestId("run-started")).toHaveTextContent("2024")
    expect(screen.getByTestId("run-ended")).toHaveTextContent("2024")
    expect(screen.getByTestId("run-duration")).toHaveTextContent("2m 30s")
  })

  /**
   * A run still open, or one whose process died before it could write an
   * ending. Saying "no end recorded" is the whole of what is known; deciding it
   * has been abandoned belongs to the reaper, which writes that decision down.
   */
  it("says no end was recorded rather than showing an empty cell", () => {
    render(<IngestionRunsTable runs={[makeRun({ status: "running", completed_at: null })]} />)

    expect(screen.getByTestId("run-no-end")).toHaveTextContent("No end recorded")
    expect(screen.queryByTestId("run-duration")).toBeNull()
    expect(screen.queryByTestId("run-ended")).toBeNull()
  })

  it("does not claim a length when the two recorded times disagree", () => {
    render(
      <IngestionRunsTable
        runs={[
          makeRun({
            started_at: "2024-03-01T09:17:30Z",
            completed_at: "2024-03-01T09:15:00Z",
          }),
        ]}
      />
    )

    expect(screen.getByTestId("run-ended")).toBeInTheDocument()
    expect(screen.getByTestId("run-no-duration")).toHaveTextContent("Length not known")
    expect(screen.queryByTestId("run-duration")).toBeNull()
  })

  it("shows an unparseable time as it arrived, keeping the fault attributable", () => {
    render(<IngestionRunsTable runs={[makeRun({ started_at: "not a date" })]} />)

    expect(screen.getByTestId("run-started")).toHaveTextContent("not a date")
  })
})

describe("IngestionRunsTable, who started an attempt", () => {
  it("prefers the email, which outlives the account", () => {
    render(
      <IngestionRunsTable
        runs={[makeRun({ started_by_email: "alex@owlcg.com", started_by_user_id: "user-9" })]}
      />
    )

    expect(screen.getByTestId("run-starter")).toHaveTextContent("alex@owlcg.com")
  })

  it("falls back to the user id when the email is gone", () => {
    render(
      <IngestionRunsTable
        runs={[makeRun({ started_by_email: null, started_by_user_id: "user-9" })]}
      />
    )

    expect(screen.getByTestId("run-starter")).toHaveTextContent("User user-9")
  })

  it("says it was not recorded rather than leaving the cell to read as nobody", () => {
    render(
      <IngestionRunsTable
        runs={[makeRun({ started_by_email: null, started_by_user_id: null })]}
      />
    )

    expect(screen.getByTestId("run-starter")).toHaveTextContent("Not recorded")
  })
})

describe("IngestionRunsTable, what an attempt left behind", () => {
  it("shows what broke it, when something did", () => {
    render(
      <IngestionRunsTable
        runs={[makeRun({ status: "failed", error: "Statement page 4 could not be read" })]}
      />
    )

    expect(screen.getByTestId("run-error")).toHaveTextContent(
      "Statement page 4 could not be read"
    )
  })

  it("shows nothing where there is no error", () => {
    render(<IngestionRunsTable runs={[makeRun({ error: null })]} />)

    expect(screen.queryByTestId("run-error")).toBeNull()
  })

  it("treats an empty error string as no error, not as a blank line", () => {
    render(<IngestionRunsTable runs={[makeRun({ error: "" })]} />)

    expect(screen.queryByTestId("run-error")).toBeNull()
  })

  it("shows the notes recorded against the attempt", () => {
    render(<IngestionRunsTable runs={[makeRun({ notes: "Reprocessed after the fix" })]} />)

    expect(screen.getByTestId("run-notes")).toHaveTextContent("Reprocessed after the fix")
  })

  it("shows nothing where there are no notes", () => {
    render(<IngestionRunsTable runs={[makeRun({ notes: null })]} />)

    expect(screen.queryByTestId("run-notes")).toBeNull()
  })
})
