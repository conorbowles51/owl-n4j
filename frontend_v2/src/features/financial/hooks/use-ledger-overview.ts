import { useQuery } from "@tanstack/react-query"
import { financialAPI } from "../api"
import { useInvestigationScope } from "../stores/investigation-scope"
import { usePaymentCategory } from "./use-payment-categories"

/**
 * The Overview's headline figures for the scope and categories the page shows, from the server: the same figures
 * the page would add up from every payment (useInvestigatorPayments), without waiting for every payment.
 * Under the case's "financial-ledger" key, so every write that refreshes the ledger refreshes these too.
 */
export function useLedgerOverview(caseId: string) {
  const [categories] = usePaymentCategory(caseId)
  const [params] = useInvestigationScope(caseId)
  return useQuery({
    queryKey: ["financial-ledger", caseId, "overview", params ?? null, categories],
    queryFn: async () => {
      const result = await financialAPI.getLedgerOverview({
        caseId,
        accountId: params?.accountId,
        accountIds: params?.accountIds,
        accountHolders: params?.accountHolders,
        startDate: params?.startDate,
        endDate: params?.endDate,
        categories,
      })
      if (result.case_id !== caseId) throw Error("The figures came from a different case.")
      return result
    },
    // The previous answer stays up only for the same case and categories (a scope change keeps it until the new
    // one lands, as the ledger does); figures for other categories are never shown as these.
    placeholderData: (previous, query) =>
      query?.queryKey[1] === caseId && JSON.stringify(query?.queryKey[4]) === JSON.stringify(categories)
        ? previous
        : undefined,
    enabled: !!caseId,
  })
}
