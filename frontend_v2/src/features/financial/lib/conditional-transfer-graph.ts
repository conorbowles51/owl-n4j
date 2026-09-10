import type { TransferInputs } from "./ledger-transfers"
import type { PostingGraph } from "./ledger-graph"
export function conditionalTransferGraph(
  scope: TransferInputs,
  pairs: { debit_id: string; credit_id: string }[]
) {
  const rows = new Map(scope.rows.map((r) => [r.key, r]))
  const nodes = new Map<string, PostingGraph["nodes"][number]>()
  const used = new Set<string>()
  const edges = pairs.map((pair) => {
    const debit = rows.get(pair.debit_id),
      credit = rows.get(pair.credit_id)
    if (
      !debit ||
      !credit ||
      debit.direction !== "debit" ||
      credit.direction !== "credit" ||
      debit.account_id === credit.account_id ||
      debit.currency !== credit.currency ||
      debit.amount_minor !== credit.amount_minor ||
      used.has(debit.key) ||
      used.has(credit.key)
    )
      throw Error("Transfer graph differs from the captured pairings.")
    used.add(debit.key)
    used.add(credit.key)
    for (const row of [debit, credit])
      nodes.set(row.account_id, {
        id: row.account_id,
        account_id: row.account_id,
        kind: "account",
        label: row.account_label ?? `Account ${row.account_id.slice(0, 8)}`,
      })
    return {
      id: debit.key,
      transaction_id: debit.key,
      source: debit.account_id,
      target: credit.account_id,
      source_document_id: debit.source_document_id,
      currency: debit.currency,
      amount_minor: debit.amount_minor,
      direction: debit.direction,
      ordering_date: debit.ordering_date,
      description: `Conditional transfer to ${credit.account_label ?? credit.account_id}`,
      credit_id: credit.key,
      credit_ordering_date: credit.ordering_date,
    }
  })
  return { nodes: [...nodes.values()], edges }
}
