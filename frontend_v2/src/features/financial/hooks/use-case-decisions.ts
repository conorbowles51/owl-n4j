/**
 * Reading back what a case decided.
 *
 * Follows `use-ingestion-runs.ts` rather than inventing a second shape: a
 * `useQuery` over one `financialAPI` call, keyed on the case and the filters,
 * disabled until there is a case. The one thing this read has that the runs
 * read does not is paging, and everything below that is not in the runs hook
 * is there because of it.
 *
 * **Its own query key, not the ledger's.** `["financial-decisions", ...]` sits
 * outside `["financial-ledger", ...]` for a stronger reason than the one
 * `use-ledger-transactions.ts` gives for sitting outside the graph's. The log
 * is appended to and never edited, it outlives the things it is about -- a
 * purge writes its decision and then deletes the row that decision was about
 * -- and it records decisions on subjects that are not ledger rows at all,
 * `evidence_file` being the clearest. Sharing the ledger's prefix would refetch
 * the whole history every time a list of rows was read, and would imply the two
 * move together when a decision survives its subject.
 *
 * **The page envelope is handed back whole, not unpacked.** The `queryFn`
 * returns the `DecisionsResponse` exactly as it arrived, which is the
 * pass-through shape both sibling reads use. `use-row-adjudication.ts`
 * composes its reading instead, and the reason it has to does not apply here:
 * `rescues_period` is said in that response and in no other place, so a caller
 * handed the raw object could render the outcome and lose it. Nothing in this
 * response is like that. `total` and `truncated` are fields on the envelope,
 * so returning the envelope is what delivers them, and a hook that returned
 * `decisions` alone would be the failure to avoid -- it would throw away the
 * fact that the history was cut short, which is the one thing this read exists
 * to be honest about. `describeDecisionPage` in `lib/decision-format.ts` takes
 * the page whole for the same reason, so composing per-record readings here
 * would produce a shape the function written for this page no longer fits.
 *
 * **No polling, and no keeping the previous page on screen.** No polling for
 * the reason the runs hook gives. No `placeholderData` because holding the last
 * page's rows while the next one loads puts them under a sentence describing
 * the page that was asked for: "Showing 101 to 200" over rows 1 to 100. A
 * history screen that misdescribes which part of the history is on screen is
 * the precise failure this whole surface is built to avoid, and a loading state
 * is honest. What would reverse this: a panel that tracks for itself which page
 * the rows it is showing belong to, at which point the trade is only about
 * flicker.
 *
 * **What invalidates this key, and what deliberately does not.**
 * `use-row-adjudication.ts` invalidates `["financial-decisions", caseId]`
 * alongside the ledger's key, because a quarantine and a release each append
 * to this log and the cached page would otherwise be a decision short of the
 * one the person just took. That is the only writer wired to it today. Every
 * other route that appends here -- a supersession, a restore, a purge, a
 * reclassification -- has no mutation hook in this build yet, so nothing is
 * missing from this list so much as not written; each of them closes its own
 * half when it lands, the way this one did.
 */

import { useQuery } from "@tanstack/react-query"
import {
  financialAPI,
  type AdjudicationDecision,
  type AdjudicationSubject,
} from "../api"

export interface CaseDecisionQueryParams {
  /**
   * Narrow to decisions about one kind of thing. Left unset means every kind.
   */
  subjectType?: AdjudicationSubject
  /**
   * Narrow to one subject. May be given without `subjectType`; the records
   * each name their own kind and the read is scoped to the case either way.
   * See `financialAPI.getCaseDecisions`.
   */
  subjectId?: string
  /** Narrow to one decision in the vocabulary. Left unset means every one. */
  decision?: AdjudicationDecision
  /**
   * At most this many, newest first. The bounds are the backend's and are
   * deliberately not mirrored here; a limit above the cap is capped and
   * answered rather than refused, so read the page size from the response.
   */
  limit?: number
  /** How many matching decisions to skip. Zero is a real request for the first page. */
  offset?: number
}

/**
 * One page of the case's decision log.
 *
 * Every parameter is forwarded with `?.` and nothing else. That looks like a
 * detail and is not: `limit: 0` and `offset: 0` are meaningful requests, and a
 * truthiness guard anywhere on this path -- `params?.offset || undefined` --
 * would swallow them and turn an explicit request for the first page into a
 * default. `getCaseDecisions` guards its own query string with `!== undefined`
 * for exactly that reason, and a coercion here would undo it one layer up
 * while looking like it was doing nothing.
 */
export function useCaseDecisions(
  caseId: string | undefined,
  params?: CaseDecisionQueryParams
) {
  return useQuery({
    queryKey: ["financial-decisions", caseId, params ?? null],
    queryFn: () =>
      financialAPI.getCaseDecisions({
        caseId: caseId!,
        subjectType: params?.subjectType,
        subjectId: params?.subjectId,
        decision: params?.decision,
        limit: params?.limit,
        offset: params?.offset,
      }),
    enabled: !!caseId,
  })
}
