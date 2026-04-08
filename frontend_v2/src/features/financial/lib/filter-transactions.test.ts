import { describe, expect, it } from "vitest"
import type { Transaction } from "../api"
import {
  applyDirectionalEntitySelections,
  buildEntityFlowRows,
  filterTransactionsBase,
} from "./filter-transactions"

function makeTransaction(overrides: Partial<Transaction>): Transaction {
  const {
    financial_view_mode,
    is_evidence_backed_transaction,
    ...rest
  } = overrides

  if (financial_view_mode === "intelligence") {
    return {
      financial_view_mode: "intelligence",
      is_evidence_backed_transaction: false,
      key: rest.key || "tx-1",
      amount: rest.amount ?? 100,
      financial_record_kind: rest.financial_record_kind || "transaction",
      is_financial_event: rest.is_financial_event ?? true,
      from_entity: rest.from_entity ?? { key: "sender-a", name: "Sender A" },
      to_entity: rest.to_entity ?? { key: "beneficiary-a", name: "Beneficiary A" },
      ...rest,
    } as Transaction
  }

  return {
    financial_view_mode: "transaction",
    is_evidence_backed_transaction: is_evidence_backed_transaction ?? true,
    key: rest.key || "tx-1",
    amount: rest.amount ?? 100,
    financial_record_kind: rest.financial_record_kind || "transaction",
    is_financial_event: rest.is_financial_event ?? true,
    from_entity: rest.from_entity ?? { key: "sender-a", name: "Sender A" },
    to_entity: rest.to_entity ?? { key: "beneficiary-a", name: "Beneficiary A" },
    ...rest,
  } as Transaction
}

describe("filterTransactionsBase", () => {
  it("matches search terms against AI summary content", () => {
    const transactions = [
      makeTransaction({
        key: "tx-summary",
        summary: "Funds were routed through a shell company",
      }),
      makeTransaction({
        key: "tx-other",
        summary: "Routine payroll transfer",
      }),
    ]

    const result = filterTransactionsBase(transactions, {
      searchQuery: "shell company",
      selectedCategories: new Set(),
      startDate: "",
      endDate: "",
      entityFilter: null,
      minAmount: "",
      maxAmount: "",
      sortColumns: [],
    })

    expect(result.map((tx) => tx.key)).toEqual(["tx-summary"])
  })
})

describe("applyDirectionalEntitySelections", () => {
  const transactions = [
    makeTransaction({
      key: "tx-1",
      from_entity: { key: "sender-a", name: "Sender A" },
      to_entity: { key: "beneficiary-a", name: "Beneficiary A" },
    }),
    makeTransaction({
      key: "tx-2",
      from_entity: { key: "sender-b", name: "Sender B" },
      to_entity: { key: "beneficiary-a", name: "Beneficiary A" },
    }),
  ]

  it("filters by sender and beneficiary selections together", () => {
    const result = applyDirectionalEntitySelections(
      transactions,
      new Set(["sender-a"]),
      new Set(["beneficiary-a"])
    )

    expect(result.map((tx) => tx.key)).toEqual(["tx-1"])
  })
})

describe("buildEntityFlowRows", () => {
  const transactions = [
    makeTransaction({
      key: "tx-1",
      amount: 150,
      from_entity: { key: "sender-a", name: "Sender A" },
      to_entity: { key: "beneficiary-a", name: "Beneficiary A" },
    }),
    makeTransaction({
      key: "tx-2",
      amount: -250,
      from_entity: { key: "sender-a", name: "Sender A" },
      to_entity: { key: "beneficiary-b", name: "Beneficiary B" },
    }),
    makeTransaction({
      key: "tx-3",
      amount: 400,
      from_entity: { key: "sender-b", name: "Sender B" },
      to_entity: { key: "beneficiary-b", name: "Beneficiary B" },
    }),
  ]

  it("cross-filters sender rows by selected beneficiaries", () => {
    const rows = buildEntityFlowRows(
      transactions,
      "from",
      new Set(["beneficiary-b"])
    )

    expect(rows).toEqual([
      { key: "sender-b", name: "Sender B", count: 1, totalAmount: 400 },
      { key: "sender-a", name: "Sender A", count: 1, totalAmount: 250 },
    ])
  })
})
