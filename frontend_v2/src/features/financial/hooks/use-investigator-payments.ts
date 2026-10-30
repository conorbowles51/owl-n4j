import { useMemo } from "react"
import { usePaymentCategory, matchesCategories } from "./use-payment-categories"
import { useLedgerTransactions } from "./use-ledger-transactions"
import { useInvestigationScope } from "../stores/investigation-scope"

type Ledger = NonNullable<ReturnType<typeof useLedgerTransactions>["data"]>

// Checked once per answer and case, shared by every component that reads the ledger (d5b330d1: 27,673 rows, six
// readers, re-checked on every render before).
const checked = new WeakMap<Ledger, Map<string, boolean>>()

export function isCompleteLedger(data: Ledger | undefined, caseId: string) {
  if (!data) return false
  let byCase = checked.get(data)
  if (!byCase) checked.set(data, (byCase = new Map()))
  let complete = byCase.get(caseId)
  if (complete === undefined) {
    complete =
      data.case_id === caseId &&
      new Set(data.transactions.map((row) => row.key)).size ===
        data.transactions.length &&
      data.total === data.transactions.length &&
      data.transactions.every((row) => row.case_id === caseId)
    byCase.set(caseId, complete)
  }
  return complete
}

export function useInvestigatorPayments(caseId: string) {
  const [categories] = usePaymentCategory(caseId)
  const [params, setParams] = useInvestigationScope(caseId)
  const query = useLedgerTransactions(caseId, params)
  const complete = isCompleteLedger(query.data, caseId)
  // The same array while the answer and categories are the same, so the readers' memos over it hold.
  const rows = useMemo(
    () =>
      complete
        ? query.data!.transactions.filter((row) =>
            matchesCategories(row, categories)
          )
        : [],
    [complete, query.data, categories]
  )
  return { query, params, setParams, complete, rows }
}
