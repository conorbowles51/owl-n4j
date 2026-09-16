import { useLedgerTransactions } from "./use-ledger-transactions"
import { useInvestigationScope } from "../stores/investigation-scope"
export function useInvestigatorPayments(caseId: string) {
  const [params, setParams] = useInvestigationScope(caseId)
  const query = useLedgerTransactions(caseId, params)
  const complete =
    !!query.data &&
    query.data.case_id === caseId &&
    new Set(query.data.transactions.map((row) => row.key)).size ===
      query.data.transactions.length &&
    query.data.total === query.data.transactions.length &&
    query.data.transactions.every((row) => row.case_id === caseId)
  return {
    query,
    params,
    setParams,
    complete,
    rows: complete ? query.data!.transactions : [],
  }
}
