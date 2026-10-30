/**
 * How many ledger rows a `useLedgerTransactions` read will return, counted by
 * the server without reading the rows (`/ledger-count`, same filters). The
 * Transactions page shows it while the rows load, so a long first load says
 * what it is loading.
 */

import { useQuery } from "@tanstack/react-query"
import { financialAPI } from "../api"
import type { LedgerQueryParams } from "./use-ledger-transactions"

export function useLedgerCount(
  caseId: string | undefined,
  params?: LedgerQueryParams
) {
  return useQuery({
    queryKey: ["financial-ledger-count", caseId, params ?? null],
    queryFn: () =>
      financialAPI.getLedgerCount({
        caseId: caseId!,
        sourceDocumentId: params?.sourceDocumentId,
        accountId: params?.accountId,
        accountIds: params?.accountIds,
        accountHolders: params?.accountHolders,
        ledgerStatus: params?.ledgerStatus,
        startDate: params?.startDate,
        endDate: params?.endDate,
      }),
    enabled: !!caseId,
    retry: false,
  })
}
