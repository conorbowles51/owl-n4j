import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { FinancialAccessContext } from "../hooks/use-financial-access"
import type { Transaction } from "../api"
import { TransactionTable } from "./TransactionTable"

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
  expect(screen.getByText(/125.5 \(currency not recorded\)/)).toBeVisible()
  expect(screen.queryByText("$125.50")).not.toBeInTheDocument()
})
