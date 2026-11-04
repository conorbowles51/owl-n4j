/**
 * The People & businesses list from the server (`/ledger-people-view`), so the page does not wait for every payment.
 *
 * The key sits under `["financial-ledger", caseId, ...]`, so every write that refreshes the case's ledger reads
 * refreshes this too. Its data has no `transactions`, so code that patches cached ledger rows in place leaves it
 * alone and the next read fetches it again.
 */
import { useQuery } from "@tanstack/react-query"
import { financialAPI } from "../api"
import type { LedgerQueryParams } from "./use-ledger-transactions"

export function useLedgerPeopleView(
  caseId: string,
  params: LedgerQueryParams,
  categories: string[],
  group: string,
  enabled: boolean
) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, params, "people-view", categories, group],
    queryFn: () =>
      financialAPI.getLedgerPeopleView({ caseId, ...params, categories, group: group || undefined }),
    enabled: !!caseId && enabled,
    retry: false,
    // The last answer stays while the next is worked out, so the list's controls stay on screen; its cards are not
    // shown for the new choice (the page reads isPlaceholderData).
    placeholderData: (previous, query) =>
      query?.queryKey[1] === caseId ? previous : undefined,
  })
}
