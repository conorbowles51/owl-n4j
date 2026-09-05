/**
 * Asking that a stored ledger row be set aside, or let back in.
 *
 * One mutation, not two. `quarantineRow` and `releaseRow` take the same three
 * parameters and answer with the same shape; only the verb differs, so the
 * verb travels in the variables. Two hooks would give a screen two `isPending`
 * flags and two `data` objects for one button, and the bug that follows is a
 * screen reading the answer to the call it did not make. What would reverse
 * this: a screen that genuinely needs a quarantine and a release in flight at
 * the same time, which no screen in the plan does.
 *
 * **A refusal is a resolved promise.** The endpoint turns exactly two outcomes
 * into HTTP errors, `not_found` into a 404 and `write_failed` into a 500.
 * Everything else arrives with a 200, including `refused`, which is the answer
 * "this row cannot be set aside and here is why" rather than a failure of the
 * request. So `isSuccess` on this mutation means the question was answered, not
 * that anything changed, and a caller that treats it as confirmation will tell
 * a person a row was held when it was not. The fact a caller wants is
 * `data.applied`.
 *
 * The answer is read whole before it is handed back. `mutationFn` maps the wire
 * object through `readRowAdjudication`, so `data` and the promise from
 * `mutateAsync` are both a `RowAdjudicationReading`. That is deliberate:
 * `rescues_period` is said in this response and nowhere else, never in the
 * adjudication log, and a caller handed the raw object can render the outcome
 * and drop it without noticing. Composing here removes the chance. It is safe
 * to do inside `mutationFn` because the readers cannot throw — an unrecognised
 * vocabulary member comes back labelled as unrecognised rather than raising —
 * so a mapping cannot masquerade as a request that failed.
 *
 * Invalidation is `["financial-ledger", caseId]` and nothing wider, matching
 * `use-ledger-ingest.ts`. The key is a prefix of every ledger list, the
 * admitted one and the quarantined one alike, which is exactly right here: an
 * adjudication does not add or remove a row, it moves one from one of those
 * lists to the other, so both are wrong afterwards. The Neo4j hooks under
 * `["financial", caseId, ...]` are a different store and are not touched; a
 * status change on a relational row does not change a graph node.
 *
 * `reason` is passed through unexamined. The backend requires the field and
 * does not require it to say anything, and this is not the layer to invent a
 * rule the ledger does not have. Where the field is filled in is where an empty
 * one should be caught.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query"
import { financialAPI } from "../api"
import {
  readRowAdjudication,
  type RowAdjudicationReading,
} from "../lib/adjudication-format"

/** Which of the two routes to call. */
export type AdjudicationAction = "quarantine" | "release"

export interface RowAdjudicationVariables {
  transactionId: string
  action: AdjudicationAction
  /**
   * The person's grounds, as they wrote them. Stored on the adjudication and
   * shown next to the row, so it is read afterwards as their words.
   */
  reason: string
}

/**
 * True when this answer means the ledger's contents changed under it.
 *
 * Two sources, and either one is enough. `applied` is the backend's own flag
 * and is the fact a person is told; `outcome.changedTheRow` is this build's
 * reading of the outcome word. They cannot disagree on a backend of the same
 * version, and `readRowAdjudication` already raises `appliedDisagreesWithOutcome`
 * when they do here. For deciding whether to refetch, though, a disagreement
 * should not be resolved by picking one: refetching when nothing moved costs a
 * request, and failing to refetch when something did leaves a row on screen in
 * a list it has left, which a person then reads as the ledger's answer. The
 * costs are not symmetrical, so the wider condition wins.
 *
 * This is not the same question as what to report. What a person is shown about
 * whether the row moved comes from `applied` alone.
 */
function ledgerContentsMoved(reading: RowAdjudicationReading): boolean {
  return reading.applied || reading.outcome.changedTheRow === true
}

/**
 * Set a row aside, or let one back in.
 *
 * Rejects rather than calling when there is no case. The sibling ingest hook
 * asserts its `caseId` instead, which is tolerable on a path that only reads a
 * file; this one writes something that changes what a case's totals count, and
 * a write addressed to `case_id=undefined` is not a request worth making.
 */
export function useRowAdjudication(caseId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation<RowAdjudicationReading, Error, RowAdjudicationVariables>({
    mutationFn: async (variables) => {
      if (!caseId) {
        throw new Error(
          "No case is open, so there is no ledger to change. Open the case and try again."
        )
      }
      const params = {
        caseId,
        transactionId: variables.transactionId,
        reason: variables.reason,
      }
      const result =
        variables.action === "quarantine"
          ? await financialAPI.quarantineRow(params)
          : await financialAPI.releaseRow(params)
      return readRowAdjudication(result)
    },
    onSuccess: (reading) => {
      if (!ledgerContentsMoved(reading)) return
      queryClient.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
    },
  })
}
