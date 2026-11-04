/**
 * The Trends page's figures from the server (`/ledger-trends-view`), so the page does not wait for every payment.
 *
 * The key sits under `["financial-ledger", caseId, ...]`, so every write that refreshes the case's ledger reads
 * refreshes this too. Its data has no `transactions`, so code that patches cached ledger rows in place leaves it
 * alone and the next read fetches it again.
 */
import { useQuery } from "@tanstack/react-query"
import { financialAPI } from "../api"
import type { LedgerQueryParams } from "./use-ledger-transactions"
import type { DateRange } from "../lib/investigation-trends"

export interface TrendsAsk {
  group: string
  earlier: DateRange | null
  later: DateRange | null
}

export function useLedgerTrendsView(
  caseId: string,
  params: LedgerQueryParams,
  categories: string[],
  ask: TrendsAsk,
  enabled: boolean
) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, params, "trends-view", categories, ask],
    queryFn: () =>
      financialAPI.getLedgerTrendsView({
        caseId,
        ...params,
        categories,
        group: ask.group || undefined,
        earlier: ask.earlier,
        later: ask.later,
      }),
    enabled: !!caseId && enabled,
    retry: false,
  })
}
