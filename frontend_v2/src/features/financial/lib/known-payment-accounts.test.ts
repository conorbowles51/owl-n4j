import { expect, it } from "vitest"
import { candidateAccounts } from "./candidate-contract"
import { knownAccountGroup, knownPaymentAccounts } from "./known-payment-accounts"
import { paymentInventory } from "./payment-inventory"
import { paymentFixture } from "./payment-fixture.test-support"

const period = { id: "jan", source_document_id: "source-jan", start: "2026-01-01", end: "2026-01-31", currency: "EUR" }
const items = candidateAccounts.parse({ case_id: "case", has_more: false, items: [
  { id: "eur", canonical_id: "eur", identifier: "00123", holder: "Example Company", institution: "BBVA Mexico", currency: "EUR", account_type: "checking", statement_periods: [period] },
  { id: "alias", canonical_id: "eur", identifier: null, holder: null, institution: null, currency: null, account_type: null, statement_periods: [period, { ...period, id: "feb", source_document_id: "source-feb", start: "2026-02-01", end: "2026-02-28" }] },
  { id: "card", identifier: "0099", holder: "Other Company", institution: "Card Bank", currency: "EUR", account_type: "credit_card", statement_periods: [period] },
  { id: "pending", identifier: "00200", holder: "Example Company", institution: "BBVA México", currency: "GBP", account_type: null, statement_periods: [] },
] }).items

it("retains canonical identity and every distinct registered period without inferring a payment or balance", () => {
  const result = knownPaymentAccounts(items, {})
  expect(result.accounts).toHaveLength(3)
  expect(result.accounts[0]).toMatchObject({ id: "eur", currency: "EUR", accountType: "checking", label: "BBVA Mexico · 00123 · Example Company" })
  expect(result.accounts[0].periods.map((entry) => entry.id)).toEqual(["jan", "feb"])
  expect(knownAccountGroup(result.accounts[0])).toBe("EUR:bank")
  expect(knownAccountGroup(result.accounts[1])).toBe("EUR:card")
  expect(knownAccountGroup(result.accounts[2])).toBe("GBP:unknown")
  expect(paymentInventory([], result.accounts)).toMatchObject({ currencies: ["EUR", "GBP"], first: null, last: null, banks: ["BBVA México", "Card Bank"] })
})

it("matches bank aliases, holder and canonical/alias selections together and filters exact recorded dates and sources", () => {
  const scope = { accountIds: ["alias"], accountHolders: ["bank:bbva", "example company"], startDate: "2026-02-01", endDate: "2026-02-28" }
  const result = knownPaymentAccounts(items, scope)
  expect(result.accounts).toHaveLength(1)
  expect(result.accounts[0].periods.map((entry) => entry.id)).toEqual(["feb"])
  expect(knownPaymentAccounts(items, scope, ["source-jan"]).accounts).toEqual([])
  expect(knownPaymentAccounts(items, scope, ["source-feb"]).accounts).toHaveLength(1)
  expect(knownPaymentAccounts(items, { ...scope, accountHolders: ["bank:card bank"] }).accounts).toEqual([])
})

it("does not treat missing dates as zero activity in a requested window or infer dates from payments", () => {
  const result = knownPaymentAccounts(items, { startDate: "2026-03-01", endDate: "2026-03-31" })
  expect(result.accounts).toEqual([])
  expect(result.unknownDates).toBe(1)
  const inventory = paymentInventory([{ ...paymentFixture, account_id: "pending", currency: "GBP", ordering_date: "2026-03-05" }], result.accounts)
  expect(inventory.accounts).toHaveLength(1)
  expect(inventory.currencies).toEqual(["GBP"])
})

it("uses saved period currency even when the account header is blank and does not count an alias twice", () => {
  const result = knownPaymentAccounts([{ ...items[0], currency: null }, items[1]], {})
  expect(result.accounts).toHaveLength(1)
  expect(result.accounts[0].currency).toBe("EUR")
  const inventory = paymentInventory([{ ...paymentFixture, account_id: "alias", canonical_account_id: "eur", currency: "EUR", account_institution: "BBVA Mexico" }], result.accounts)
  expect(inventory.accounts).toHaveLength(1)
  expect(inventory.banks).toHaveLength(1)
})

it("retains an account with no currency for identity counts and records which currencies lack dates", () => {
  const unknown = { ...items[0], id: "unknown", canonical_id: "unknown", currency: null, statement_periods: [] }
  const result = knownPaymentAccounts([unknown, items[3]], {})
  expect(result.accounts).toHaveLength(2)
  expect(result.accounts.find((account) => account.id === "unknown")?.currency).toBe("")
  const inventory = paymentInventory([], result.accounts)
  expect(inventory.accounts).toHaveLength(2)
  expect(inventory.banks).toHaveLength(1)
  expect(inventory.currencies).toEqual(["GBP"])
  const dates = knownPaymentAccounts([unknown, items[3]], { startDate: "2026-01-01", endDate: "2026-01-31" })
  expect(dates.accounts).toEqual([])
  expect(dates.unknownDateAccounts).toEqual([{ id: "unknown", currencies: [] }, { id: "pending", currencies: ["GBP"] }])
  expect(dates.unknownDateAccounts.filter((account) => account.currencies.includes("EUR"))).toEqual([])
})
