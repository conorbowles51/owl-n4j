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
 * Invalidation is two keys, `["financial-ledger", caseId]` and
 * `["financial-decisions", caseId]`, and nothing wider than either. The first
 * matches `use-ledger-ingest.ts` and is a prefix of every ledger list, the
 * admitted one and the quarantined one alike, which is exactly right here: an
 * adjudication does not add or remove a row, it moves one from one of those
 * lists to the other, so both are wrong afterwards. The Neo4j hooks under
 * `["financial", caseId, ...]` are a different store and are not touched; a
 * status change on a relational row does not change a graph node.
 *
 * The second key is separate from the first and has to be, for the reason
 * `use-case-decisions.ts` gives for keeping them apart: the log is appended to
 * and outlives the rows it is about, so a decisions read is not a ledger read
 * under another name. It is invalidated here because both routes append to that
 * log -- `quarantine_row.py` writes the decision on `quarantined` and the
 * reversal on `released`, and nothing at all on `unchanged`, `refused`,
 * `not_found` or `write_failed`. Without this, a person who sets a row aside
 * with the decisions screen open watches the record fail to grow by the entry
 * they just made, and reads that as the record's answer.
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
import type { RowChange } from "../lib/ledger-format"

/**
 * Which of the two routes to call.
 *
 * An alias rather than a second declaration of the same two words. The change
 * a person can ask for is decided from the row's status by
 * `changeAvailableFor`, and if that vocabulary and this one were written out
 * separately they could be edited apart without anything failing.
 */
export type AdjudicationAction = RowChange

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
 * True when this answer means the case's record of decisions grew.
 *
 * Three sources, and any one is enough, for the same asymmetry
 * `ledgerContentsMoved` is built on. The two outcomes that move the row,
 * `quarantined` and `released`, are exactly the two that append to the log --
 * that is read off `quarantine_row.py`, where every other outcome states that
 * nothing was appended -- so `ledgerContentsMoved` already covers both cases
 * that matter. `adjudicationId` is the identifier of the entry that was
 * written, null on every outcome that wrote none, and it is the backend saying
 * directly what the other two say by implication.
 *
 * Kept as a separate predicate rather than reusing the ledger one, even though
 * today they answer alike on every outcome the vocabulary has. They are two
 * different questions about two different stores, and a future member of the
 * vocabulary that records a finding without moving a row -- which is what
 * `explain_balance_failure` already is elsewhere in the log -- would make them
 * diverge. One predicate serving both would then be silently wrong for
 * whichever store it was not written for.
 */
function decisionWasRecorded(reading: RowAdjudicationReading): boolean {
  return ledgerContentsMoved(reading) || reading.adjudicationId !== null
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
      if (ledgerContentsMoved(reading)) {
        queryClient.invalidateQueries({
          queryKey: ["financial-ledger", caseId],
        })
        queryClient.invalidateQueries({ queryKey: ["ledger-source", caseId] })
        queryClient.invalidateQueries({
          queryKey: ["statement-import-status", caseId],
        })
        queryClient.invalidateQueries({
          queryKey: ["financial-linked-payments", caseId],
        })
      }
      if (decisionWasRecorded(reading)) {
        queryClient.invalidateQueries({
          queryKey: ["financial-decisions", caseId],
        })
      }
    },
  })
}
