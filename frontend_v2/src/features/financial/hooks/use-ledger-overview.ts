import { useEffect, useRef } from "react"
import { useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query"
import { financialAPI } from "../api"
import { useInvestigationScope } from "../stores/investigation-scope"
import { usePaymentCategory } from "./use-payment-categories"
import { orderOverviewPanels } from "../lib/overview-panels"

/**
 * The Overview's headline figures for the scope and categories the page shows, from the server: the same figures
 * the page would add up from every payment (useInvestigatorPayments), without waiting for every payment.
 * Under the case's "financial-ledger" key, so every write that refreshes the ledger refreshes these too.
 */
export function useLedgerOverview(caseId: string, active = true) {
  const [categories] = usePaymentCategory(caseId)
  const [params] = useInvestigationScope(caseId)
  const queryKey = ["financial-ledger", caseId, "overview", params ?? null, categories]
  const query = useQuery({
    queryKey,
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
  useRefreshWhenShown(query, queryKey, active)
  return query
}

/**
 * The Overview stays mounted while another tab is shown, and a save there (a name, a category) updates the
 * ledger's rows in place and only marks these figures out of date without fetching them. When the Overview is shown
 * again with its figures out of date, they are fetched again (the page says it is updating meanwhile).
 */
function useRefreshWhenShown(
  query: { refetch: () => Promise<unknown> },
  queryKey: QueryKey,
  active: boolean
) {
  const client = useQueryClient()
  const shown = useRef(active)
  const { refetch } = query
  useEffect(() => {
    // Only at the moment the Overview is shown again: a failed fetch also marks a query out of date, so checking on
    // every render would ask again and again while the server keeps failing.
    const wasShown = shown.current
    shown.current = active
    if (active && !wasShown && client.getQueryState(queryKey)?.isInvalidated === true) void refetch()
  })
}

/**
 * The Overview's lower panels for the scope and categories the page shows, from the server (the same figures the
 * page would work out from every payment), ordered as the page orders them. Under the case's "financial-ledger"
 * key, so every write that refreshes the ledger refreshes these too. Figures for other categories are never shown
 * as these; while the scope changes the previous answer stays up, as the ledger's does.
 */
export function useLedgerOverviewPanels(caseId: string, active = true) {
  const [categories] = usePaymentCategory(caseId)
  const [params] = useInvestigationScope(caseId)
  const queryKey = ["financial-ledger", caseId, "overview-panels", params ?? null, categories]
  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const result = await financialAPI.getLedgerOverviewPanels({
        caseId,
        accountId: params?.accountId,
        accountIds: params?.accountIds,
        accountHolders: params?.accountHolders,
        startDate: params?.startDate,
        endDate: params?.endDate,
        categories,
      })
      if (result.case_id !== caseId) throw Error("The payments came from a different case.")
      return orderOverviewPanels(result)
    },
    placeholderData: (previous, query) =>
      query?.queryKey[1] === caseId && JSON.stringify(query?.queryKey[4]) === JSON.stringify(categories)
        ? previous
        : undefined,
    enabled: !!caseId,
  })
  useRefreshWhenShown(query, queryKey, active)
  return query
}
