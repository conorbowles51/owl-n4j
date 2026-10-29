import { expect, it } from "vitest"
import { paymentInventory } from "./payment-inventory"
import { paymentFixture } from "./payment-fixture.test-support"
it("counts the complete dataset using canonical IDs, preserving unknowns and currency/date coverage", () => {
  const rows = Array.from({ length: 125 }, (_, n) => ({
    ...paymentFixture,
    key: `row-${n}`,
    account_id: `a${n}`,
    account_label: `Example ${n}`,
    account_institution: ["Bank One", "Bank Two", "Bank Three"][n % 3],
    currency: n % 2 ? "USD" : "EUR",
    ordering_date: n % 2 ? "2026-01-01" : "2025-10-31",
  }))
  const data = paymentInventory([
    ...rows,
    {
      ...rows[0],
      key: "alias",
      account_id: "alias",
      canonical_account_id: "a0",
    },
    {
      ...rows[1],
      key: "unknown",
      account_id: "unknown",
      account_institution: "",
      from_name: "",
      to_name: "",
      ordering_date_context: "statement_end_ordering_only",
    },
  ])
  expect(data.accounts).toHaveLength(126)
  expect(data.banks).toHaveLength(3)
  expect(data.currencies).toEqual(["EUR", "USD"])
  expect(data.first).toBe("2025-10-31")
  expect(data.last).toBe("2026-01-01")
  expect(data.undated).toBe(1)
  expect(data.unknownBanks).toBe(1)
  expect(data.unidentifiedCounterparties).toBeGreaterThanOrEqual(1)
})

it("counts a known account's bank as unknown only when none of its payments names one", () => {
  const known = (id: string, institution = "") => ({ id, label: id, currency: "USD", institution, periods: [] })
  const data = paymentInventory(
    [
      { ...paymentFixture, key: "1", account_id: "named", account_institution: "" },
      { ...paymentFixture, key: "2", account_id: "named", account_institution: "Bank One" },
      { ...paymentFixture, key: "3", account_id: "canonical-alias", canonical_account_id: "via-alias", account_institution: "Bank Two" },
      { ...paymentFixture, key: "4", account_id: "blank", account_institution: " " },
    ],
    [known("named"), known("via-alias"), known("blank"), known("no-payments"), known("directory", "Bank Three")] as never
  )
  // "named" still counts once from its blank row; "blank" and "no-payments" have no bank anywhere.
  expect(data.unknownBanks).toBe(3)
  expect(data.banks).toEqual(["Bank One", "Bank Three", "Bank Two"])
})
