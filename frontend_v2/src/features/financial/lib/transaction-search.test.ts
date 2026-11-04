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
describe("payment numbers (FEAT-006)", () => {
  const numbered = { ...row, txn_number: 412 }
  it.each(["#412", "no. 412", "No.412"])("finds payment number 412 with %s", (query) =>
    expect(transactionSearch(query).matches(numbered)).toBe(true)
  )
  it("finds only that number, not a longer one that contains it", () => {
    expect(transactionSearch("#41").matches(numbered)).toBe(false)
    expect(transactionSearch("#4120").matches(numbered)).toBe(false)
  })
  it("searches the number as a field in boolean mode", () =>
    expect(transactionSearch("number:412 AND loan", "boolean").matches(numbered)).toBe(true)
  )
  it("a bare number or an amount does not match on the payment number", () => {
    expect(transactionSearch("412").matches({ ...numbered, description: "rent", amount_minor: "100" })).toBe(false)
    expect(transactionSearch("no.").matches({ ...numbered, description: "rent" })).toBe(false)
  })
  it("#1 does not match longer numbers written in the text", () => {
    expect(transactionSearch("#1").matches({ ...row, description: "Store #1234", txn_number: 9 })).toBe(false)
    expect(transactionSearch("#12").matches({ ...row, description: "Store #12 Main St", txn_number: 9 })).toBe(true)
    expect(transactionSearch("#1").matches({ ...row, description: "Store #1234 and #1", txn_number: 9 })).toBe(true)
  })
  it("#1234 written in a description is still found", () =>
    expect(transactionSearch("#1234").matches({ ...row, description: "Cheque #1234", txn_number: 9 })).toBe(true)
  )
  it("a row not numbered yet is not found by a number", () =>
    expect(transactionSearch("#412").matches({ ...row, txn_number: null })).toBe(false)
  )
})
