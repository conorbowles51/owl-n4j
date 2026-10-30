import { describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"

const ledger = { current: undefined as unknown }
vi.mock("./use-ledger-transactions", () => ({ useLedgerTransactions: () => ({ data: ledger.current }) }))
vi.mock("../stores/investigation-scope", () => ({ useInvestigationScope: () => [{}, () => {}] }))
const categories = ["all"]
vi.mock("./use-payment-categories", () => ({
  usePaymentCategory: () => [categories, () => {}],
  matchesCategories: (row: { category?: string }) => row.category !== "hidden",
}))

import { isCompleteLedger, useInvestigatorPayments } from "./use-investigator-payments"

type Ledger = Parameters<typeof isCompleteLedger>[0]
type Row = { key: string; case_id: string }
type Answer = { case_id: string; transactions: Row[]; total: number }

const row = (key: string, extra = {}): Row => ({ key, case_id: "c1", ...extra })
const answer = (transactions: Row[], extra = {}): Answer => ({ case_id: "c1", transactions, total: transactions.length, ...extra })
// The check as it was written inline before.
const before = (data: Answer | undefined, caseId: string) =>
  !!data &&
  data.case_id === caseId &&
  new Set(data.transactions.map((r) => r.key)).size === data.transactions.length &&
  data.total === data.transactions.length &&
  data.transactions.every((r) => r.case_id === caseId)
const keys = (rows: unknown[]) => (rows as Row[]).map((r) => r.key)

describe("useInvestigatorPayments", () => {
  it("keeps the same rows between renders, so the readers' memos over them hold", () => {
    ledger.current = answer([row("a"), row("b", { category: "hidden" }), row("c")])
    const view = renderHook(() => useInvestigatorPayments("c1"))
    const first = view.result.current.rows
    view.rerender()
    expect(view.result.current.rows).toBe(first)
    expect(keys(first)).toEqual(["a", "c"])
    ledger.current = answer([row("a")])
    view.rerender()
    expect(keys(view.result.current.rows)).toEqual(["a"])
  })

  it("decides completeness as before, once per answer and case", () => {
    const cases = [
      undefined,
      answer([row("a"), row("b")]),
      answer([row("a"), row("a")]),
      answer([row("a")], { total: 2 }),
      answer([row("a")], { case_id: "c2" }),
      answer([row("a"), { key: "b", case_id: "c2" }]),
      answer([]),
    ]
    for (const data of cases)
      for (const caseId of ["c1", "c2"]) expect(isCompleteLedger(data as unknown as Ledger, caseId)).toBe(before(data, caseId))
    const data = answer([row("a")])
    const spy = vi.spyOn(data.transactions, "every")
    isCompleteLedger(data as unknown as Ledger, "c1")
    isCompleteLedger(data as unknown as Ledger, "c1")
    expect(spy).toHaveBeenCalledTimes(1)
  })
})
