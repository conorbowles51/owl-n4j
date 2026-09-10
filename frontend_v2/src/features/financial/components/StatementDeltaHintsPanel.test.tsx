import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementDeltaHintsPanel } from "./StatementDeltaHintsPanel"
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Opened source {transactionId}</p>
  ),
}))
it("shows a lead as an arithmetic possibility and opens its exact source", () => {
  render(
    <StatementDeltaHintsPanel
      caseId="case"
      currency="GBP"
      hints={{
        available: true,
        difference_minor: "2000",
        rows_checked: 2,
        limitation: "Arithmetic leads only, not findings.",
        signatures: [],
        candidates: [
          {
            transaction_id: "row",
            ref_id: "TX-A",
            amount_minor: "2000",
            direction: "credit",
            kind: "extra_entry",
            explanation:
              "Removing this amount would close the difference arithmetically.",
          },
        ],
      }}
    />
  )
  expect(screen.getByText(/Arithmetic leads only/)).toBeInTheDocument()
  expect(screen.getByText("TX-A: 20.00 GBP credit")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Inspect lead TX-A" }))
  expect(screen.getByText("Opened source row")).toBeInTheDocument()
})
it("does not convert no matching lead into a clean statement", () => {
  render(
    <StatementDeltaHintsPanel
      caseId="case"
      currency="GBP"
      hints={{
        available: true,
        difference_minor: "1",
        rows_checked: 2,
        limitation: "Unexplained difference remains.",
        signatures: [],
        candidates: [],
      }}
    />
  )
  expect(screen.getByText(/No checked row amount/)).toBeInTheDocument()
  expect(screen.getByText(/difference of 0.01 GBP/)).toBeInTheDocument()
})
