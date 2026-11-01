import { expect, it, vi } from "vitest"
import type { LedgerTransaction } from "../api"
import { paymentFixture } from "./payment-fixture.test-support"
import { connectionGroups, connectionGroupsInSteps } from "./overview-panels"

const payment = (key: string, fields: Partial<LedgerTransaction>): LedgerTransaction => ({
  ...paymentFixture,
  key,
  currency: "USD",
  account_type: "checking",
  amount_minor: "100",
  counterparty_link: null,
  ...fields,
} as LedgerTransaction)

// Follow the money and the Overview draw the same figures: these are the old MoneyConnections' groups, names,
// accounts, unnamed payments and totals, written out.
it("works out the connections the page has always shown, per currency and account type", () => {
  const rows = [
    payment("in", { direction: "credit", from_name: "Ana", to_name: "Owner", amount_minor: "300",
      label_sources: { from_name: { source: "description" } } as LedgerTransaction["label_sources"] }),
    payment("out", { direction: "debit", from_name: "Owner", to_name: "Ana", amount_minor: "120" }),
    payment("tax", { direction: "debit", from_name: "Owner", to_name: "", counterparty_raw: null, description: "C20 IVA COM", amount_minor: "1.5" }),
    payment("card", { direction: "debit", from_name: "Owner", to_name: "Shop", account_type: "credit_card", currency: "MXN" }),
  ]
  const groups = connectionGroups(rows)
  expect(groups.map((group) => group.group)).toEqual(["MXN:card", "USD:bank"])
  const bank = groups[1]
  expect([bank.credit_total, bank.debit_total]).toEqual(["300", null])
  expect(bank.names).toEqual([{ id: "name:Ana", name: "Ana",
    credit: { keys: ["in"], total: "300", suggested: true },
    debit: { keys: ["out"], total: "120", suggested: false } }])
  expect(bank.accounts.map((account) => account.keys)).toEqual([["in", "out", "tax"]])
  expect(bank.unnamed.map((item) => [item.direction, item.kind, item.keys, item.total])).toEqual([["debit", "tax", ["tax"], null]])
  expect(groups[0].names.map((name) => name.name)).toEqual(["Shop"])
})

it("works out the same connections in steps, giving the browser a turn between them, and stops for a newer list", async () => {
  const rows = Array.from({ length: 60 }, (_, index) =>
    payment(`p${index}`, {
      direction: index % 2 ? "credit" : "debit",
      from_name: index % 2 ? `Payer ${index % 7}` : "Owner",
      to_name: index % 2 ? "Owner" : `Payee ${index % 5}`,
      currency: ["USD", "MXN", "EUR"][index % 3],
      account_type: index % 4 ? "checking" : "credit_card",
      amount_minor: String(100 + index),
    })
  )
  // Every step "runs past" the time budget, so it gives a turn after each one and reports it.
  let clock = 0
  const spy = vi.spyOn(performance, "now").mockImplementation(() => (clock += 100))
  try {
    const seen: [number, number][] = []
    const groups = await connectionGroupsInSteps(rows, (done, total) => seen.push([done, total]))
    expect(JSON.stringify(groups)).toBe(JSON.stringify(connectionGroups(rows)))
    expect(seen).toEqual([1, 2, 3, 4, 5, 6, 7, 8].map((done) => [done, 8]))
    const signal = { cancelled: false }
    const stopped = connectionGroupsInSteps(rows, () => (signal.cancelled = true), signal)
    expect(await stopped).toBeNull()
  } finally {
    spy.mockRestore()
  }
})
