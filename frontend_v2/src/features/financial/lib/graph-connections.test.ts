import { expect, it } from "vitest"
import { paymentConnections } from "./graph-connections"
import { postingGraph, type PostingGraph } from "./ledger-graph"

it("keeps all 25000 exact amounts and payment IDs while combining only matching connections", () => {
  const edges: PostingGraph["edges"] = Array.from(
    { length: 25000 },
    (_, i) => ({
      id: `payment-${i}`,
      transaction_id: `payment-${i}`,
      source: "account",
      target: `name-${i % 3}`,
      direction: "debit",
      currency: i % 3 === 0 ? "EUR" : "USD",
      amount_minor: "9007199254740993",
      source_document_id: "document",
      ordering_date: "2026-01-01",
      description: "Payment",
      proof_class: "p3",
    })
  )
  const graph = postingGraph.parse({
    case_id: "case",
    account_id: null,
    start_date: null,
    end_date: null,
    population: "working",
    snapshot_sha256: "a".repeat(64),
    applied: false,
    limitation: "",
    excluded_rows: 0,
    nodes: [
      {
        id: "account",
        kind: "account",
        account_id: "account",
        label: "Account",
      },
      ...Array.from({ length: 3 }, (_, i) => ({
        id: `name-${i}`,
        kind: "source_label",
        account_id: "account",
        label: `Name ${i}`,
      })),
    ],
    edges,
  })
  const connections = paymentConnections(graph.edges)
  expect(connections).toHaveLength(3)
  expect(new Set(connections.flatMap((edge) => edge.payment_ids))).toEqual(
    new Set(edges.map((edge) => edge.id))
  )
  expect(
    connections.reduce((total, edge) => total + BigInt(edge.amount_minor), 0n)
  ).toBe(25000n * 9007199254740993n)
  expect(edges[0].amount_minor).toBe("9007199254740993")
  expect(
    paymentConnections([
      edges[0],
      {
        ...edges[0],
        source: edges[0].target,
        target: edges[0].source,
        direction: "credit",
      },
      { ...edges[0], currency: "GBP" },
    ])
  ).toHaveLength(3)
})
