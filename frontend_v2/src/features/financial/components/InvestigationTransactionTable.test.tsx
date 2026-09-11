import { fireEvent, render, screen, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import {
  InvestigationTransactionTable,
  PaymentTotals,
} from "./InvestigationTransactionTable"
import type { LedgerTransaction } from "../api"
const row = {
  key: "payment",
  ref_id: "TX-1",
  description: "Rent",
  currency: "EUR",
  direction: "debit",
  amount_minor: "120000",
  running_balance_minor: "50000",
  ordering_date: "2026-09-01",
  counterparty_raw: "Landlord",
} as LedgerTransaction
it("opens the original payment and selects it without needing technical columns", () => {
  const open = vi.fn(),
    toggle = vi.fn()
  render(
    <InvestigationTransactionTable
      rows={[row]}
      selected={[]}
      onOpen={open}
      onToggle={toggle}
    />
  )
  fireEvent.click(screen.getByRole("button", { name: "Open transaction" }))
  expect(open).toHaveBeenCalledWith(row)
  fireEvent.click(screen.getByRole("checkbox", { name: /Select Rent/ }))
  expect(toggle).toHaveBeenCalledWith(row, true)
  expect(screen.queryByText("P3")).not.toBeInTheDocument()
})
it("totals exact amounts separately by currency and identifies unreadable amounts", () => {
  render(
    <PaymentTotals
      label="Selected"
      rows={[
        row,
        {
          ...row,
          key: "usd",
          currency: "USD",
          direction: "credit",
          amount_minor: "9007199254740993",
        },
        { ...row, key: "bad", amount_minor: NaN },
      ]}
    />
  )
  expect(screen.getByText("1,200.00 EUR")).toBeInTheDocument()
  expect(
    screen.getByText(/1 transactions could not be totalled/)
  ).toBeInTheDocument()
  expect(screen.getAllByText("90,071,992,547,409.93 USD")).toHaveLength(2)
})
it("keeps card debt separate from bank movements in the same currency", () => {
  render(
    <PaymentTotals
      label="Selected"
      rows={[
        row,
        {
          ...row,
          key: "card",
          account_type: "credit_card",
          amount_minor: "4000",
        },
      ]}
    />
  )
  const bank = screen.getByText("Money out").parentElement!
  const card = screen.getByText("Card charges").parentElement!
  expect(within(bank).getByText("1,200.00 EUR")).toBeInTheDocument()
  expect(within(card).getByText("40.00 EUR")).toBeInTheDocument()
  expect(screen.queryByText("1,240.00 EUR")).not.toBeInTheDocument()
})
