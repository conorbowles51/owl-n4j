import { createContext, useContext } from "react"
import type { LedgerTransaction } from "../api"
import type { Judgement } from "../lib/judgements"

/**
 * The judgements on payment rows being shown, looked up per row. A saved statement provides its own; the case
 * provider covers the whole ledger from one read. The tables read this to put a marker under the payment's
 * description; outside a provider they show nothing.
 */
export const RowJudgements = createContext<{
  caseId: string
  lookup: (transaction: Pick<LedgerTransaction, "key" | "source_document_id">) => Judgement[]
  onCorrect?: (judgement: Judgement, transaction: LedgerTransaction) => void
  /** A list of judgement calls (the ledger's "With a judgement call" filter): rows are tinted by their tier. */
  tint?: boolean
  /** Only these calls count for the tint and order (the ledger's active judgement sub-filters). */
  calls?: (transaction: LedgerTransaction) => Judgement[]
} | null>(null)

/** The calls touching a payment, from the nearest provider (null outside one). */
export function useRowJudgementLookup() {
  return useContext(RowJudgements)?.lookup ?? null
}

/** In a list of judgement calls: the row's most urgent tier (1 first), else 0. */
export function useRowPriority(transaction: LedgerTransaction) {
  const context = useContext(RowJudgements)
  if (!context?.tint) return 0
  const items = (context.calls || context.lookup)(transaction)
  return items.length ? Math.min(...items.map((item) => item.priority || 1)) : 0
}

