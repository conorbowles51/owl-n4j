import { expect, it } from "vitest"
import { entryBalances, type QueueEntry } from "./review-queue"

const entry = (values: Partial<QueueEntry>) =>
  ({ currency: "USD", period_start: "2021-01-01", period_end: "2021-01-31", ...values }) as QueueEntry

it("states the printed opening and closing balances as read, scaled to the statement's currency", () => {
  expect(
    entryBalances(entry({ opening_minor: "100000", closing_minor: "95050", transaction_count: 12, balance_status: "matches" }))
  ).toBe("opening 1,000.00 USD · closing 950.50 USD · 12 payments read · balances add up")
  expect(entryBalances(entry({ currency: "JPY", opening_minor: "5000", closing_minor: "-20", transaction_count: 1 }))).toBe(
    "opening 5,000 JPY · closing -20 JPY · 1 payment read"
  )
})

it("never shows a missing balance as zero, and never guesses decimals without a currency", () => {
  expect(entryBalances(entry({ opening_minor: null, closing_minor: "0", balance_status: "difference" }))).toBe(
    "opening not read · closing 0.00 USD · balances do not add up"
  )
  expect(entryBalances(entry({ currency: "", opening_minor: "95050", closing_minor: undefined }))).toBe(
    "opening 95,050 (minor units; currency not chosen) · closing not read"
  )
})
