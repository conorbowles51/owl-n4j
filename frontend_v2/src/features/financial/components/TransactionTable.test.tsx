import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { FinancialAccessContext } from "../hooks/use-financial-access"
import type { Transaction } from "../api"
import { TransactionTable } from "./TransactionTable"
import { useFinancialStore } from "../stores/financial.store"
beforeEach(() =>
  useFinancialStore.setState({
    expandedRowKeys: new Set(),
    checkedKeys: new Set(),
  })
)

const record: Transaction = {
  key: "amount-claim",
  name: "Receipt amount",
  amount: 125.5,
  currency: "EUR",
  from_entity: { key: null, name: null },
  to_entity: { key: null, name: null },
  financial_record_kind: "allegation",
  financial_view_mode: "intelligence",
  is_financial_event: true,
  is_evidence_backed_transaction: false,
}
function show(canEdit = true, tx = record) {
  const correct = vi.fn()
  render(
    <FinancialAccessContext.Provider
      value={{ canEdit, canUpload: false, ready: true, error: false }}
    >
      <TooltipProvider>
        <TransactionTable
          mode="intelligence"
          transactions={[tx]}
          allTransactions={[tx]}
          categories={[]}
          sortColumns={[]}
          onCategorize={vi.fn()}
          onAmountClick={correct}
          onEntityEdit={vi.fn()}
          onGroupSubTransactions={vi.fn()}
          onRemoveFromGroup={vi.fn()}
          onSaveDetails={vi.fn()}
        />
      </TooltipProvider>
    </FinancialAccessContext.Provider>
  )
  return correct
}
it("opens amount correction for other evidence and uses its recorded currency", () => {
  const correct = show()
  expect(screen.getByText("€125.50")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Correct amount for Receipt amount" })
  )
  expect(correct).toHaveBeenCalledExactlyOnceWith(record)
})
it("does not offer an enabled amount or category edit to a read-only user", () => {
  show(false)
  expect(
    screen.getByRole("button", { name: "Correct amount for Receipt amount" })
  ).toBeDisabled()
  expect(screen.getByRole("combobox")).toBeDisabled()
})
it("does not invent dollars when the source currency is missing", () => {
  show(true, { ...record, currency: undefined })
  expect(screen.getByText(/125.50 \(currency not recorded\)/)).toBeVisible()
  expect(screen.queryByText("$125.50")).not.toBeInTheDocument()
})

it("opens readable details from the record name without offering unused selection or editing controls", () => {
  show(true, {
    ...record,
    purpose: "Reported equipment purchase",
    notes: "Compare the original receipt",
    currency: undefined,
  })
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Open record Receipt amount" })
  ).toHaveAttribute("aria-expanded", "false")
  fireEvent.click(screen.getByRole("button", { name: "Receipt amount" }))
  expect(
    screen.getByRole("region", { name: "Record details for Receipt amount" })
  ).toBeVisible()
  expect(screen.getByText("Reported equipment purchase")).toBeVisible()
  expect(screen.getByText("Compare the original receipt")).toBeVisible()
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  expect(screen.queryByText("legacy")).not.toBeInTheDocument()
  expect(screen.queryByText("$125.50")).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Close record Receipt amount" })
  )
  expect(
    screen.queryByRole("region", { name: "Record details for Receipt amount" })
  ).not.toBeInTheDocument()
})

it("keeps an unfamiliar source currency visible when its details are opened", () => {
  show(false, { ...record, currency: "Unknown unit" })
  fireEvent.click(
    screen.getByRole("button", { name: "Open record Receipt amount" })
  )
  expect(
    screen.getByRole("region", { name: "Record details for Receipt amount" })
  ).toHaveTextContent("125.50 Unknown unit")
})
