import { render, screen, within } from "@testing-library/react"
import { expect, it } from "vitest"
import { PaymentTotals } from "./InvestigationTransactionTable"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import type { KnownPaymentAccount } from "../lib/known-payment-accounts"

const account: KnownPaymentAccount = {
  id: "eur", label: "Example Bank · 0001 · Example Company", institution: "Example Bank", currency: "EUR", accountType: "checking",
  periods: [{ id: "period", source_document_id: "source", start: "2026-01-01", end: "2026-01-31", currency: "EUR" }],
}
it("shows zero recorded EUR bank and card payments beside actual USD amounts without fabricating transactions", () => {
  render(<PaymentTotals label="Current scope" rows={[{ ...paymentFixture, account_id: "usd", currency: "USD", amount_minor: "12500", direction: "credit", account_type: "checking", account_institution: "Other Bank" }]} knownAccounts={[account, { ...account, id: "card", accountType: "credit_card" }]} />)
  expect(screen.getByRole("heading", { name: "Current scope · 1 transactions · 3 accounts · 2 banks" })).toBeVisible()
  const bank = screen.getByRole("region", { name: "EUR · Bank accounts" })
  expect(bank).toHaveTextContent("0 transactions · 1 account")
  expect(within(bank).getAllByText("0.00 EUR")).toHaveLength(3)
  expect(bank).toHaveTextContent("Saved statements are available")
  const card = screen.getByRole("region", { name: "EUR · Credit cards" })
  expect(card).toHaveTextContent("0 transactions · 1 account")
  expect(card).toHaveTextContent("Change in card debt")
  expect(screen.getByRole("region", { name: "USD · Bank accounts" })).toHaveTextContent("125.00 USD")
  expect(screen.getByText(/zero does not confirm no activity/)).toBeVisible()
})

it("keeps accounts awaiting saved periods and unknown account types explicit", () => {
  render(<PaymentTotals label="Current scope" rows={[]} knownAccounts={[{ ...account, accountType: null, periods: [] }]} />)
  const section = screen.getByRole("region", { name: "EUR · Account type not recorded" })
  expect(section).toHaveTextContent("0 transactions · 1 account")
  expect(section).toHaveTextContent("No saved statement period is recorded")
  expect(section).toHaveTextContent("pending reading or review")
  expect(section).not.toHaveTextContent("Money in")
  expect(screen.getByText(/No printed dates available/)).toBeVisible()
})

it("does not count known metadata as another account or change money already recorded on an alias", () => {
  render(<PaymentTotals label="Current scope" rows={[{ ...paymentFixture, account_id: "alias", canonical_account_id: "eur", currency: "EUR", amount_minor: "700", direction: "debit", account_type: undefined, account_institution: "Example Bank" }]} knownAccounts={[{ ...account, accountType: null }]} />)
  expect(screen.getByRole("heading", { name: "Current scope · 1 transactions · 1 accounts · 1 banks" })).toBeVisible()
  expect(screen.queryByRole("region", { name: "EUR · Account type not recorded" })).not.toBeInTheDocument()
  const totals = screen.getByRole("region", { name: "EUR · Bank accounts" })
  expect(totals).toHaveTextContent("7.00 EUR")
  expect(totals).toHaveTextContent("-7.00 EUR")
})

it("counts currency-unknown accounts and banks without creating a zero monetary group", () => {
  render(<PaymentTotals label="Current scope" rows={[]} knownAccounts={[{ ...account, currency: "", periods: [] }]} />)
  expect(screen.getByRole("heading", { name: "Current scope · 0 transactions · 1 accounts · 1 banks" })).toBeVisible()
  expect(screen.getByLabelText("Accounts with currency not recorded")).toHaveTextContent("1 known account")
  expect(screen.getByText(/Currencies: Not recorded/)).toBeVisible()
  const summary = screen.getByRole("region", { name: "Current scope" })
  expect(within(summary).queryByRole("region")).not.toBeInTheDocument()
  expect(summary).not.toHaveTextContent("0.00")
  expect(summary).toHaveTextContent("Currency not recorded")
})
