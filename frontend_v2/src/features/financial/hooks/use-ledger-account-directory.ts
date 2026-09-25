import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateAccounts, candidateUrl } from "../lib/candidate-contract"

// Shared by the account selectors and the recorded-account summary. Both need
// the complete directory, not just the first page or accounts with payments.
export function useLedgerAccountDirectory(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, "account-filter-directory"],
    enabled: !!caseId,
    queryFn: async () => {
      const items = []
      let offset = 0
      let pending: { name: string; count: number }[] = []
      let pendingTruncated = false
      for (;;) {
        const data = candidateAccounts.parse(await fetchAPI(
          `${candidateUrl("ledger-accounts", caseId!)}&offset=${offset}`
        ))
        assertCandidateScope(data, caseId!)
        items.push(...data.items)
        if (offset === 0) {
          pending = data.pending_holders
          pendingTruncated = data.pending_directory_truncated
        }
        if (!data.has_more) return { items, pending, pendingTruncated }
        if (!data.items.length) throw Error("The account list could not be fully loaded.")
        offset += data.items.length
      }
    },
  })
}
