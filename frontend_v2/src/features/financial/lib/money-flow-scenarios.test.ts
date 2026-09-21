import { expect, it } from "vitest"
import { paymentFixture } from "./payment-fixture.test-support"
import {
  allocateReceipts,
  receiptCluster,
  impliedExchangeRate,
} from "./money-flow-scenarios"
const row = (
  key: string,
  amount: string,
  direction: string,
  day: string,
  extra = {}
) => ({
  ...paymentFixture,
  key,
  amount_minor: amount,
  direction,
  ordering_date: `2026-01-${day}`,
  description: key,
  ...extra,
})
const a = row("a", "10000", "credit", "01"),
  b = row("b", "5000", "credit", "02"),
  c = row("c", "7000", "debit", "03"),
  d = row("d", "6000", "debit", "04")
it("FIFO and LIFO conserve the source receipts without allocating later money backwards", () => {
  const fifo = allocateReceipts([a, b, c, d], "fifo").allocations,
    lifo = allocateReceipts([a, b, c, d], "lifo").allocations
  expect(fifo.map((x) => [x.receipt.key, x.payment.key, x.amount])).toEqual([
    ["a", "c", 7000n],
    ["a", "d", 3000n],
    ["b", "d", 3000n],
  ])
  expect(lifo.map((x) => [x.receipt.key, x.payment.key, x.amount])).toEqual([
    ["b", "c", 5000n],
    ["a", "c", 2000n],
    ["a", "d", 6000n],
  ])
  const early = row("early", "20000", "debit", "01")
  expect(allocateReceipts([early, b], "fifo").unfunded[0].amount).toBe(20000n)
})
it("keeps currencies and accounts apart and excludes card, missing-date and replaced readings", () => {
  const result = allocateReceipts(
    [
      a,
      c,
      row("foreign", "900", "credit", "02", { currency: "USD" }),
      row("card", "100", "credit", "02", { account_type: "credit_card" }),
      row("undated", "100", "credit", "02", {
        ordering_date_context: "statement_end_ordering_only",
      }),
      row("other", "100", "credit", "02", { account_id: "other" }),
      row("old", "100", "credit", "02", { ledger_status: "superseded" }),
    ],
    "lifo"
  )
  expect(result.allocations.map((x) => x.receipt.key)).toEqual(["a"])
})
it("clusters are timing candidates, with an explicit window and smaller outgoing amounts", () => {
  expect(
    receiptCluster(
      [a, b, c, d, row("large", "11000", "debit", "02")],
      a,
      2
    ).map((r) => r.key)
  ).toEqual(["c"])
})
it("shows exact implied rates across currency scales without claiming a market quote", () => {
  const sent = row("sent", "10000", "debit", "01", { currency: "USD" })
  const received = row("received", "14500", "credit", "02", { currency: "JPY" })
  expect(impliedExchangeRate(sent, received)).toBe("145.00000000")
  expect(impliedExchangeRate(received, sent)).toBeNull()
  expect(
    impliedExchangeRate(sent, { ...received, ordering_date: "2025-01-01" })
  ).toBeNull()
})
