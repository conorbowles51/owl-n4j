import { expect, it } from "vitest"
import { transferInputs } from "./ledger-transfers"
import { conditionalTransferGraph } from "./conditional-transfer-graph"
export const scope = transferInputs.parse({
  case_id: "case",
  start_date: null,
  end_date: null,
  population: "working",
  tolerance_days: 3,
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Synthetic",
  excluded_rows: 0,
  date_unavailable_ids: [],
  candidates: [],
  rows: [
    ...[
      ["d", "a", "debit"],
      ["c", "b", "credit"],
      ["d2", "b", "debit"],
      ["c2", "c", "credit"],
    ].map(([key, account_id, direction]) => ({
      key,
      account_id,
      direction,
      case_id: "case",
      account_label: account_id,
      source_document_id: "source",
      currency: "GBP",
      amount_minor: "9007199254740993",
      ordering_date: "2026-01-01",
      description: "Synthetic",
    })),
  ],
})
export const pairs = [
  { debit_id: "d", credit_id: "c" },
  { debit_id: "d2", credit_id: "c2" },
]
it("connects account paths only through selected pairings while preserving exact amounts", () => {
  const graph = conditionalTransferGraph(scope, pairs)
  expect(graph.nodes.map((n) => n.id)).toEqual(["a", "b", "c"])
  expect(graph.edges.map((e) => [e.source, e.target, e.amount_minor])).toEqual([
    ["a", "b", "9007199254740993"],
    ["b", "c", "9007199254740993"],
  ])
  expect(graph.edges.map((e) => e.credit_id)).toEqual(["c", "c2"])
  expect(conditionalTransferGraph(scope, [])).toEqual({ nodes: [], edges: [] })
})
it("refuses duplicate, missing, reversed and inconsistent paired postings", () => {
  for (const invalid of [
    [pairs[0], pairs[0]],
    [{ debit_id: "missing", credit_id: "c" }],
    [{ debit_id: "c", credit_id: "d" }],
  ])
    expect(() => conditionalTransferGraph(scope, invalid)).toThrow()
  for (const patch of [
    { currency: "USD" },
    { amount_minor: "9007199254740992" },
    { account_id: "a" },
  ])
    expect(() =>
      conditionalTransferGraph(
        {
          ...scope,
          rows: scope.rows.map((r) => (r.key === "c" ? { ...r, ...patch } : r)),
        },
        pairs
      )
    ).toThrow()
})
