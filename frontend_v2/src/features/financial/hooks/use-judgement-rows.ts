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
} | null>(null)

/** The calls touching a payment, from the nearest provider (null outside one). */
export function useRowJudgementLookup() {
  return useContext(RowJudgements)?.lookup ?? null
}

