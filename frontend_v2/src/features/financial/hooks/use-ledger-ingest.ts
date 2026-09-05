/**
 * Reading a bank file, and putting what it holds into the ledger.
 *
 * Two mutations rather than a query and a mutation. Precheck stores nothing
 * and could be modelled as a query, but it is not one: it runs when a person
 * asks for it, against a window that person just typed, and running it again
 * with the same window is a repeat of an action rather than a refresh of a
 * view. Cached under a query key it would go stale against a window the reader
 * has since changed, which is the one thing about it that must not happen.
 *
 * Invalidation is `["financial-ledger", caseId]` and nothing wider. The Neo4j
 * hooks in `use-financial-data.ts` sit under `["financial", caseId, ...]` and
 * are a different store; an ingest writes relational rows and cannot change a
 * graph node, so refetching the graph here would imply a relationship the
 * write path does not have. See the header of `use-ledger-transactions.ts`,
 * which draws the same line from the other side.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  financialAPI,
  type FileIngestion,
  type FilePrecheck,
  type IngestWindowParams,
} from "../api"

export type PrecheckVariables = Omit<IngestWindowParams, "caseId">

export type IngestVariables = PrecheckVariables & {
  documentType?: string
  institutionName?: string
}

/**
 * Ask what a file holds, without storing any of it.
 *
 * Answers with a `FilePrecheck` for every outcome the evidence can cause, and
 * throws only for the three the endpoint turns into statuses: a file this case
 * cannot see, a window that is not a window, and a fault. So a caller that
 * reads `data.outcome` is reading the normal case, and `error` genuinely means
 * something other than the file is wrong.
 */
export function usePrecheckFile(caseId: string | undefined) {
  return useMutation<FilePrecheck, Error, PrecheckVariables>({
    mutationFn: (variables) =>
      financialAPI.precheckFile({ caseId: caseId!, ...variables }),
  })
}

/**
 * Read the file again and keep it.
 *
 * The ledger is invalidated only when rows were actually written. Every other
 * outcome left the ledger exactly as it was, and `already_ingested` in
 * particular reports `stored: false` while being a perfectly good answer, so
 * invalidating on "no error" would refetch the ledger for a call that changed
 * nothing.
 */
export function useIngestFile(caseId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation<FileIngestion, Error, IngestVariables>({
    mutationFn: (variables) =>
      financialAPI.ingestFile({ caseId: caseId!, ...variables }),
    onSuccess: (result) => {
      if (!result.stored) return
      queryClient.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
  })
}
