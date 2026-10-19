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
