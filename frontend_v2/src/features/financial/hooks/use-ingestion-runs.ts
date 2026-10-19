/**
 * Reading the ingestion runs.
 *
 * Sits under its own query key rather than sharing the ledger's, for the same
 * reason `use-ledger-transactions.ts` sits outside the graph's: the two answer
 * different questions and neither invalidates the other. Refetching the ledger
 * does not change what an attempt recorded about itself when it ended, and
 * refetching the runs does not change a row.
 *
 * There is no polling here. A run that is still open will not update on screen
 * until something asks again, which is the same behaviour the ledger already
 * has. Adding an interval would be a decision about how often a half-finished
 * ingest is worth a request, and that has not been settled.
 */

import { useQuery } from "@tanstack/react-query"
import { financialAPI, type IngestionRunStatus } from "../api"

export interface IngestionRunQueryParams {
  /**
   * Left unset means every status, including `failed` and `aborted`. That is
   * the endpoint's default and the opposite of the ledger's, because a failed
   * attempt is the thing this read exists to surface. See
   * `financialAPI.getIngestionRuns`.
   */
  status?: IngestionRunStatus
  /** At most this many, newest first. The backend refuses anything below 1. */
  limit?: number
}

export function useIngestionRuns(
  caseId: string | undefined,
  params?: IngestionRunQueryParams
) {
  return useQuery({
    queryKey: ["financial-runs", caseId, params ?? null],
    queryFn: () =>
      financialAPI.getIngestionRuns({
        caseId: caseId!,
        status: params?.status,
        limit: params?.limit,
      }),
    enabled: !!caseId,
  })
}
