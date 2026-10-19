import type { LedgerTransaction } from "../api"
import { paymentFixture } from "./payment-fixture.test-support"
export function trendFixture(
  key: string,
  date: string,
  amount: string,
  name = "Supplier",
  extra: Partial<LedgerTransaction> = {}
): LedgerTransaction {
  return {
    ...paymentFixture,
    key,
    ref_id: `TX-${key}`,
    ordering_date: date,
    transaction_date: date,
    currency: "USD",
    direction: "debit",
    from_name: "Trading Co",
    to_name: name,
    amount_minor: amount,
    description: `Payment to ${name} (${key})`,
    account_holder: "Trading Co",
    account_label: "Trading Co · Bank A",
    account_type: "checking",
    category: "Services",
    ...extra,
  }
}
export const trendRows = [
  ...[1000, 2000, 3000, 4000, 5000].map((amount, i) =>
    trendFixture(`jan-${i}`, `2021-01-0${i + 1}`, String(amount))
  ),
  trendFixture("subscription-dec", "2020-12-10", "1299", "Software Co"),
  trendFixture("subscription-jan", "2021-01-10", "1299", "Software Co"),
  trendFixture("subscription-feb", "2021-02-10", "1299", "Software Co"),
  trendFixture("large", "2021-02-16", "90000"),
  trendFixture("new", "2021-02-17", "42000", "New supplier"),
  trendFixture("out", "2021-02-22", "1305000", "", {
    row_index: 1,
    statement_period_id: "period",
    description: "T17 SPID ENVIADO Ref. 001234 072",
  }),
  trendFixture("return", "2021-02-22", "1305000", "Trading Co", {
    row_index: 2,
    statement_period_id: "period",
    direction: "credit",
    from_name: "",
    description: "T22 SPID DEVUELTO Ref. 001234 072",
    category: "Returned transfers",
  }),
]
export const trendCoverage = {
  available: true,
  truncated: false,
  periods: [
    {
      account_id: "account",
      account_label: "Trading Co",
      start: "2020-12-01",
      end: "2021-02-28",
      source_status: "admitted",
    },
  ],
}
