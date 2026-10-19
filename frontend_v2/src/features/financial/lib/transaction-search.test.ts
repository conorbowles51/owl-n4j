import { describe, expect, it } from "vitest"
import { paymentFixture } from "./payment-fixture.test-support"
import {
  compareDisplayedAmounts,
  transactionSearch,
} from "./transaction-search"
const row = {
  ...paymentFixture,
  from_name: "Acme Holdings",
  to_name: "Example Bank",
  description: "Loan repayment, ref AA123",
  category: "Transfers",
  currency: "USD",
  amount_minor: "12345",
}
describe("transaction search", () => {
  it.each([
    "Acme",
    '"Acme Holdings" AND NOT refund',
    'from:"Acme Holdings" AND (category:Transfers OR category:Travel)',
    "(refund OR loan) AND NOT category:Travel",
    "amount:123.45",
    "currency:USD loan",
    "loan OR refund AND unknown",
  ])("matches %s", (query) => {
    expect(transactionSearch(query, "boolean").matches(row)).toBe(true)
  })
  it.each([
    "NOT loan",
    "from:Bank",
    "category:Travel OR refund",
    "(loan OR refund) AND unknown",
  ])("excludes %s", (query) =>
    expect(transactionSearch(query, "boolean").matches(row)).toBe(false)
  )
  it.each(["loan AND", "(loan", "loan)", '"loan', "from:", "unknown:value"])(
    "explains invalid %s",
    (query) => expect(transactionSearch(query, "boolean").error).toBeTruthy()
  )
  it("keeps ordinary text literal", () =>
    expect(transactionSearch("loan OR refund", "text").matches(row)).toBe(
      false
    ))
})
it("sorts displayed amounts exactly across currency exponents and large integers", () => {
  const data = [
    { ...row, key: "usd", amount_minor: "20000" },
    { ...row, key: "jpy", currency: "JPY", amount_minor: "900" },
    { ...row, key: "kwd", currency: "KWD", amount_minor: "50000" },
  ]
  expect(data.sort(compareDisplayedAmounts).map((row) => row.key)).toEqual([
    "kwd",
    "usd",
    "jpy",
  ])
  expect(
    compareDisplayedAmounts(
      { ...row, amount_minor: "9007199254740993" },
      { ...row, amount_minor: "9007199254740992" }
    )
  ).toBe(1)
})
