import { render, screen, fireEvent } from "@testing-library/react"
import { it, expect, vi } from "vitest"
import { RunningBalanceComparisonPanel } from "./RunningBalanceComparisonPanel"
import { runningBalanceComparison } from "../lib/correction-contract"
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Source transaction {transactionId}</p>
  ),
}))
const walk = {
  compared_intervals: 1,
  mismatch_count: 0,
  unanchored_balances: 0,
  excluded_rows: 0,
  trailing_rows_without_balance: 1,
  findings: [],
  findings_truncated: false,
}
it("shows conditional orders, exact differences and original source links", () => {
  const comparison = runningBalanceComparison.parse({
    available: true,
    reason: null,
    currency: "GBP",
    limitation: "Neither order nor coverage is verified.",
    interpretations: [
      {
        order: "source_row_order",
        current: walk,
        proposed: {
          ...walk,
          mismatch_count: 1,
          findings: [
            {
              before_ref: null,
              after_ref: "TX-A",
              after_transaction_id: "row-a",
              expected_minor: "9007199254740993",
              printed_minor: "9007199254740992",
              delta_minor: "-1",
            },
          ],
        },
      },
      { order: "reverse_source_row_order", current: walk, proposed: walk },
    ],
  })
  render(
    <RunningBalanceComparisonPanel caseId="case-a" comparison={comparison} />
  )
  fireEvent.click(screen.getByText("Running-balance comparison"))
  expect(screen.getByText("Assuming source row order")).toBeVisible()
  expect(screen.getByText("Assuming reverse source row order")).toBeVisible()
  expect(screen.getByText(/expected 90071992547409.93 GBP/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "View source: TX-A" }))
  expect(screen.getByText("Source transaction row-a")).toBeInTheDocument()
})
it("states unavailable rather than a zero-discrepancy pass", () => {
  render(
    <RunningBalanceComparisonPanel
      caseId="case-a"
      comparison={{
        available: false,
        reason: "No printed balances",
        interpretations: [],
      }}
    />
  )
  fireEvent.click(screen.getByText("Running-balance comparison"))
  expect(screen.getByText("No printed balances")).toBeVisible()
  expect(screen.queryByText(/0 mismatches/)).not.toBeInTheDocument()
})
