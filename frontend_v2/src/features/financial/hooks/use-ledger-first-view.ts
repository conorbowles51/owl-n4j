/**
 * The Transactions page's first view (`/ledger-first-view`): the default view's figures and one page of rows,
 * worked out by the server so the page does not wait for every payment.
 *
 * The key sits under `["financial-ledger", caseId, ...]`, so every write that refreshes the case's ledger reads
 * refreshes this too. Its data has no `transactions`, so code that patches cached ledger rows in place leaves it
 * alone and the next read fetches it again.
 */
import { useQuery } from "@tanstack/react-query"
import { financialAPI } from "../api"
import type { LedgerQueryParams } from "./use-ledger-transactions"

/** The table's "Rows per page" choices; a saved page size outside them reads every row instead. */
export const FIRST_VIEW_PAGE_SIZES = [25, 50, 100, 250]

export function useLedgerFirstView(
  caseId: string | undefined,
  params: LedgerQueryParams | undefined,
  page: number,
  pageSize: number
) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, params ?? null, "first-view", page, pageSize],
    queryFn: () =>
      financialAPI.getLedgerFirstView({
        caseId: caseId!,
        sourceDocumentId: params?.sourceDocumentId,
        accountId: params?.accountId,
        accountIds: params?.accountIds,
        accountHolders: params?.accountHolders,
        ledgerStatus: params?.ledgerStatus,
        startDate: params?.startDate,
        endDate: params?.endDate,
        page,
        pageSize,
      }),
    enabled: !!caseId,
    retry: false,
  })
}
