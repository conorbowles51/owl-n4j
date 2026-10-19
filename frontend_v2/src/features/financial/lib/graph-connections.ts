import type { PostingGraph } from "./ledger-graph"

export type PaymentConnection = PostingGraph["edges"][number] & {
  payment_ids: string[]
}

/** Aggregate for drawing only. Each payment remains attached to exactly one connection. */
export function paymentConnections(
  edges: PostingGraph["edges"]
): PaymentConnection[] {
  const connections = new Map<string, PaymentConnection>()
  for (const edge of edges) {
    const key = JSON.stringify([
      edge.source,
      edge.target,
      edge.currency,
      edge.direction,
    ])
    const previous = connections.get(key)
    if (previous) {
      previous.amount_minor = (
        BigInt(previous.amount_minor) + BigInt(edge.amount_minor)
      ).toString()
      previous.payment_ids.push(edge.transaction_id)
    } else connections.set(key, { ...edge, payment_ids: [edge.transaction_id] })
  }
  return [...connections.values()]
}
