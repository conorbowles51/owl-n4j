import { describe, expect, it } from "vitest"
import type { LedgerTransaction } from "../api"
import {
  activitySeries,
  analysisTableView,
  emptyAnalysisFilters,
  filterAnalysis,
  party,
  partyName,
  partySummaries,
  perspectiveSummary,
  sortAnalysisRows,
} from "./transaction-analysis"
import { sameTableView } from "./ledger-table-view"
const row = (key: string, values: Partial<LedgerTransaction> = {}) =>
  ({
    key,
    description: key,
    account_id: "account",
    account_holder: "Our Co",
    account_label: "Our Co · Bank",
    account_type: "checking",
    currency: "USD",
    direction: "debit",
    amount_minor: "100",
    ordering_date: "2026-01-03",
    from_name: "Our Co",
    to_name: "Supplier",
    ...values,
  }) as LedgerTransaction
const rows = [
  row("out", { amount_minor: "9007199254740993" }),
  row("in", {
    direction: "credit",
    from_name: "Client",
    to_name: "Our Co",
    amount_minor: "200",
  }),
  row("internal", { to_name: "Sister Co", amount_minor: "300" }),
  row("other", { from_name: "Other", to_name: "Supplier" }),
  row("eur", { currency: "EUR", amount_minor: "400" }),
  row("card", { account_type: "credit_card", amount_minor: "500" }),
]
describe("connected transaction analysis", () => {
  it("uses OR within each side and AND between sender, recipient and perspective selections", () => {
    const filters = {
      ...emptyAnalysisFilters,
      fromNames: ["name:Our Co", "name:Other"],
      toNames: ["name:Supplier"],
      perspectiveNames: ["name:Our Co"],
      analysisGroup: "USD:bank",
    }
    expect(filterAnalysis(rows, filters).map((r) => r.key)).toEqual(["out"])
    expect(filterAnalysis(rows, filters, "from").map((r) => r.key)).toEqual([
      "out",
    ])
    expect(filterAnalysis(rows, filters, "to").map((r) => r.key)).toEqual([
      "out",
      "internal",
    ])
    expect(
      filterAnalysis(rows, filters, "perspective").map((r) => r.key)
    ).toEqual(["out", "other"])
    expect(
      filterAnalysis(rows, { ...filters, fromNames: ["name:Missing"] })
    ).toEqual([])
  })
  it("counts each internal entry once, excludes it from external flow, and never adds currencies or card debt", () => {
    const result = perspectiveSummary(rows, ["name:Our Co", "name:Sister Co"])
    expect(result.totals).toEqual([
      {
        group: "USD:bank",
        incoming: 200n,
        outgoing: 9007199254740993n,
        internal: 300n,
        incomingCount: 1,
        outgoingCount: 1,
        internalCount: 1,
      },
      {
        group: "EUR:bank",
        incoming: 0n,
        outgoing: 400n,
        internal: 0n,
        incomingCount: 0,
        outgoingCount: 1,
        internalCount: 0,
      },
      {
        group: "USD:card",
        incoming: 0n,
        outgoing: 500n,
        internal: 0n,
        incomingCount: 0,
        outgoingCount: 1,
        internalCount: 0,
      },
    ])
    expect([...result.counterparties.get("USD:bank")!.keys()]).toEqual([
      "name:Supplier",
      "name:Client",
    ])
    const filters = {
      ...emptyAnalysisFilters,
      perspectiveNames: ["name:Our Co", "name:Sister Co"],
      flowKind: "outgoing" as const,
      flowParty: "name:Supplier",
      analysisGroup: "USD:bank",
    }
    expect(filterAnalysis(rows, filters).map((r) => r.key)).toEqual(["out"])
    expect(
      filterAnalysis(rows, filters, "perspective").map((r) => r.key)
    ).toEqual(["out", "in", "internal", "other"])
  })
  it("treats cleared names as unknown, retains labels as literal names and never invents counterparties", () => {
    expect(
      party(
        row("unknown", {
          to_name: "",
          counterparty_raw: "Not the corrected name",
        }),
        "to"
      ).key
    ).toBe("unknown:to")
    expect(party(row("fallback", { from_name: undefined }), "from").key).toBe(
      "name:Our Co"
    )
    const both = row("same", { from_name: " A  B ", to_name: "A B" })
    expect(partySummaries([both])).toMatchObject([
      { key: "name:A B", count: 1, fromCount: 1, toCount: 1 },
    ])
  })
  it("charts all exact amounts and missing months without inventing dates", () => {
    const series = activitySeries([
      row("jan", { amount_minor: "9007199254740993", category: "Rent" }),
      row("march", { ordering_date: "2026-03-03", category: "Rent" }),
      row("undated", {
        ordering_date_context: "statement_end_ordering_only",
        category: "Fees",
      }),
      row("bad", { amount_minor: NaN }),
    ])
    expect(series.months.map((m) => [m.month, m.count])).toEqual([
      ["2026-01", 1],
      ["2026-03", 1],
    ])
    expect(series.omittedEmptyMonths).toBe(true)
    expect(series.categories[0].debit).toBe(9007199254741093n)
    expect(series.undated).toBe(1)
    expect(
      filterAnalysis(rows, {
        ...emptyAnalysisFilters,
        analysisPeriod: "2026-02",
      })
    ).toEqual([])
    expect(
      filterAnalysis(rows, {
        ...emptyAnalysisFilters,
        analysisCategories: ["Uncategorized"],
      })
    ).toHaveLength(rows.length)
  })
  it("retains exact filters in export contracts including arrays, and orders names predictably", () => {
    const filters = {
      ...emptyAnalysisFilters,
      fromNames: ["name:Our Co", "name:Other"],
      analysisCategories: ["Fees", "Rent"],
    }
    const view = {
      search: "",
      currency: "",
      proof: "",
      direction: "",
      sort: "from-desc",
      ...analysisTableView(filters),
    }
    expect(sameTableView(JSON.stringify(view), view)).toBe(true)
    expect(
      sameTableView(
        JSON.stringify({ ...view, from_names: ["name:Other"] }),
        view
      )
    ).toBe(false)
    const ordered = [
      row("z", { to_name: "Zebra" }),
      row("a", { to_name: "Alpha" }),
      row("b", { to_name: "beta" }),
    ]
    sortAnalysisRows(ordered, "to-asc")
    expect(ordered.map((r) => r.key)).toEqual(["a", "b", "z"])
  })
})

it("keeps a linked counterparty distinct from an identical printed name and exports the selected identity", () => {
  const linked = row("linked", {
    to_name: "Supplier & Sons",
    counterparty_link: {
      kind: "party",
      id: "party-1",
      label: "Supplier & Sons",
    },
  })
  const unlinked = row("unlinked", { to_name: "Supplier & Sons" })
  const key = party(linked, "to").key
  expect(key).toBe("identity:party:party-1:Supplier%20%26%20Sons")
  expect(partyName(key)).toBe("Supplier & Sons")
  const filters = { ...emptyAnalysisFilters, toNames: [key] }
  expect(
    filterAnalysis([linked, unlinked], filters).map((row) => row.key)
  ).toEqual(["linked"])
  expect(analysisTableView(filters).to_names).toEqual([key])
})
