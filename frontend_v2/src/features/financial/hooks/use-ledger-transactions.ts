/**
 * Reading the relational ledger.
 *
 * `use-financial-data.ts` reads the Neo4j graph under the query key
 * `["financial", caseId, ...]`, and every mutation in that file invalidates
 * that prefix. This hook deliberately sits outside it, under
 * `["financial-ledger", ...]`, because those mutations write to the graph and
 * cannot change a relational ledger row: categorising a graph transaction or
 * correcting its amount there leaves the ledger exactly as it was. Sharing the
 * prefix would refetch the ledger on every graph edit and, worse, would imply
 * a relationship between the two stores that the write paths do not have.
 */

import { useQuery } from "@tanstack/react-query"
import { financialAPI, type LedgerStatus } from "../api"

export interface LedgerQueryParams {
  accountId?: string
  /**
   * Left unset means `admitted` — the population every total in this ledger is
   * filtered to. The default is the endpoint's, not this hook's; see
   * `financialAPI.getLedgerTransactions`.
   */
  ledgerStatus?: LedgerStatus
  /** `YYYY-MM-DD`. Bounds `ordering_date`, not any printed date. */
  startDate?: string
  /** `YYYY-MM-DD`. Bounds `ordering_date`, not any printed date. */
  endDate?: string
}

export function useLedgerTransactions(
  caseId: string | undefined,
  params?: LedgerQueryParams
) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, params ?? null],
    queryFn: () =>
      financialAPI.getLedgerTransactions({
        caseId: caseId!,
        accountId: params?.accountId,
        ledgerStatus: params?.ledgerStatus,
        startDate: params?.startDate,
        endDate: params?.endDate,
      }),
    enabled: !!caseId,
  })
}
