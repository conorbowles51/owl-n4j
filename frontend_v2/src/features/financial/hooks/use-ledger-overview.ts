import { useEffect, useRef } from "react"
import { useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query"
import { financialAPI } from "../api"
import { useInvestigationScope } from "../stores/investigation-scope"
import { usePaymentCategory } from "./use-payment-categories"
import { figureKeys, orderOverviewPanels, type PanelFigure } from "../lib/overview-panels"

/**
 * The Overview's headline figures for the scope and categories the page shows, from the server: the same figures
 * the page would add up from every payment (useInvestigatorPayments), without waiting for every payment.
 * Under the case's "financial-ledger" key, so every write that refreshes the ledger refreshes these too.
 */
type OverviewScope = ReturnType<typeof useInvestigationScope>[0]

/**
 * The Overview's headline figures query (key and fetcher), shared by the page's hook and the start-up prefetch
 * (route-data.ts), so a prefetched answer is the one the page reads.
 */
export function ledgerOverviewQuery(caseId: string, params: OverviewScope | null | undefined, categories: string[]) {
  return {
    queryKey: ["financial-ledger", caseId, "overview", params ?? null, categories] as QueryKey,
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
  }
}

/** The Overview's lower panels query (key and fetcher), shared by the page's hook and the start-up prefetch. */
export function ledgerOverviewPanelsQuery(caseId: string, params: OverviewScope | null | undefined, categories: string[]) {
  return {
    queryKey: ["financial-ledger", caseId, "overview-panel-figures", params ?? null, categories] as QueryKey,
    queryFn: async () => {
      const result = await financialAPI.getLedgerOverviewPanelFigures({ caseId, ...panelScope(params), categories })
      if (result.case_id !== caseId) throw Error("The payments came from a different case.")
      return orderOverviewPanels(result)
    },
  }
}

export function useLedgerOverview(caseId: string, active = true) {
  const [categories] = usePaymentCategory(caseId)
  const [params] = useInvestigationScope(caseId)
  const { queryKey, queryFn } = ledgerOverviewQuery(caseId, params, categories)
  const query = useQuery({
    queryKey,
    queryFn,
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
 * page would work out from every payment), ordered as the page orders them, each list of payment keys given as its
 * length (GET /ledger-overview-panel-figures; the keys are read when a figure is opened: usePanelFigureKeys). Under
 * the case's "financial-ledger" key, so every write that refreshes the ledger refreshes these too. Figures for
 * other categories are never shown as these; while the scope changes the previous answer stays up, as the
 * ledger's does.
 */
export function useLedgerOverviewPanels(caseId: string, active = true) {
  const [categories] = usePaymentCategory(caseId)
  const [params] = useInvestigationScope(caseId)
  const { queryKey, queryFn } = ledgerOverviewPanelsQuery(caseId, params, categories)
  const query = useQuery({
    queryKey,
    queryFn,
    placeholderData: (previous, query) =>
      query?.queryKey[1] === caseId && JSON.stringify(query?.queryKey[4]) === JSON.stringify(categories)
        ? previous
        : undefined,
    enabled: !!caseId,
  })
  useRefreshWhenShown(query, queryKey, active)
  return query
}

const panelScope = (params: OverviewScope | null | undefined) => ({
  accountId: params?.accountId,
  accountIds: params?.accountIds,
  accountHolders: params?.accountHolders,
  startDate: params?.startDate,
  endDate: params?.endDate,
})

/**
 * Reads the payment keys behind one figure of the Overview's panels, for the scope and categories the page shows:
 * from the whole panels answer (GET /ledger-overview-panels), read on the first open and kept under the case's
 * "financial-ledger" key, so a write reads it again. When the keys found are not as many as the figure drawn
 * (`drawn`), the panels changed since they were drawn: the whole answer is read again once, and if it still
 * differs the drawn figures are read again and this resolves null, so the page never opens a list its drawn count
 * contradicts. Resolves null too when the figure is no longer in the panels.
 */
export function usePanelFigureKeys(caseId: string) {
  const [categories] = usePaymentCategory(caseId)
  const [params] = useInvestigationScope(caseId)
  const client = useQueryClient()
  return async (figure: PanelFigure, drawn: number): Promise<string[] | null> => {
    const queryKey = ["financial-ledger", caseId, "overview-panels", params ?? null, categories]
    const read = (staleTime: number) =>
      client.fetchQuery({
        queryKey,
        staleTime,
        queryFn: async () => {
          const result = await financialAPI.getLedgerOverviewPanels({ caseId, ...panelScope(params), categories })
          if (result.case_id !== caseId) throw Error("The payments came from a different case.")
          return result
        },
      })
    let keys = figureKeys(await read(Infinity), figure)
    if (keys?.length !== drawn) {
      keys = figureKeys(await read(0), figure)
      if (keys?.length !== drawn) {
        void client.invalidateQueries({ queryKey: ["financial-ledger", caseId, "overview-panel-figures"] })
        return null
      }
    }
    return keys
  }
}
