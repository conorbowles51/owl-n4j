import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { LedgerTracingWorkbench } from "./LedgerTracingWorkbench"
import { fetchAPI } from "@/lib/api-client"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./RequestedCoveragePanel", () => ({
  RequestedCoveragePanel: () => null,
}))
vi.mock("./LedgerFilters", () => ({
  LedgerFilters: ({ onApply }: { onApply: (p: unknown) => void }) => (
    <button
      onClick={() =>
        onApply({
          accountId: "account",
          startDate: "2026-01-01",
          endDate: "2026-01-31",
        })
      }
    >
      Apply scope
    </button>
  ),
}))
const inputs = {
  case_id: "case",
  account_id: "account",
  start_date: "2026-01-01",
  end_date: "2026-01-31",
  currency: "GBP",
  snapshot_sha256: "a".repeat(64),
  included_rows: 1,
  excluded_rows: 0,
  applied: false,
  readings: [
    {
      included: true,
      row: {
        key: "row",
        ordering_date: "2026-01-15",
        direction: "credit",
        amount_minor: "100",
        description: "Deposit",
        currency: "GBP",
      },
    },
  ],
}
describe("conditional tracing workbench", () => {
  it("requires scope and explicit assumptions, with no selected method", async () => {
    vi.mocked(fetchAPI).mockResolvedValue(inputs)
    render(<LedgerTracingWorkbench caseId="case" />)
    expect(
      screen.getByRole("button", { name: "Load tracing inputs" })
    ).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
    fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
    await screen.findByText("Record your scenario assumptions")
    expect(
      screen.getByLabelText("Attributed deposit").querySelectorAll("option")
    ).toHaveLength(2)
    expect(screen.getByLabelText("Opening balance in minor units")).toHaveValue(
      ""
    )
    expect(
      screen.getByRole("button", { name: "Calculate conditional scenario" })
    ).toBeDisabled()
    screen
      .getAllByRole("checkbox")
      .forEach((box) => expect(box).not.toBeChecked())
  })
  it("refuses inputs for another case", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({ ...inputs, case_id: "other" })
    render(<LedgerTracingWorkbench caseId="case" />)
    fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
    fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("different filters")
    )
    expect(
      screen.queryByText("Record your scenario assumptions")
    ).not.toBeInTheDocument()
  })
})
