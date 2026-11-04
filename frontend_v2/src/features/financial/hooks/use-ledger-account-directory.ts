import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateAccounts, candidateUrl } from "../lib/candidate-contract"

// Shared by the account selectors and the recorded-account summary. Both need
// the complete directory, not just the first page or accounts with payments.
export function useLedgerAccountDirectory(caseId: string | undefined) {
  return useQuery({ ...ledgerAccountDirectoryQuery(caseId), enabled: !!caseId })
}

/** Key and fetcher shared by the hook and the start-up prefetch (route-data.ts). */
export function ledgerAccountDirectoryQuery(caseId: string | undefined) {
  return {
    queryKey: ["financial-ledger", caseId, "account-filter-directory"],
    queryFn: async () => {
      const items = []
      let offset = 0
      let pending: { name: string; count: number }[] = []
      let pendingTruncated = false
      // The first request asks for every account at once (one request, not one per 100 accounts after each
      // other); more pages follow only if accounts were added while it was answered. If the whole list cannot be
      // answered at once (the statement period limit applies per answer), it is read 100 accounts at a time.
      let whole = true
      for (;;) {
        let answer: unknown
        try {
          answer = await fetchAPI(
            `${candidateUrl("ledger-accounts", caseId!)}&offset=${offset}${whole ? "&whole=true" : ""}`
          )
        } catch (error) {
          if (!whole) throw error
          whole = false
          continue
        }
        whole = false
        const data = candidateAccounts.parse(answer)
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
  }
}
