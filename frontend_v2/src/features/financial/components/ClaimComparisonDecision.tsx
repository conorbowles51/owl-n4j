import { useFinancialAccess } from "../hooks/use-financial-access"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import {
  type VerifiedClaimComparison,
  claimVerdictLabel,
  orderClaimCandidates,
} from "../lib/claim-comparison"
import { claimReviewNote } from "../lib/claim-review-note"
import { correctionMoney } from "../lib/correction-contract"
function ClaimComparisonDecisionForm({
  report,
}: {
  report: VerifiedClaimComparison
}) {
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    report.value.case_id,
    `claim-review:${JSON.stringify(report.value.inputs)}`,
    {
      decision: "",
      reason: "",
      selected: [] as string[],
      reviewedHash: report.envelope.scenario_sha256,
    }
  )
  const { decision, reason, selected } = draft
  const recalculated = draft.reviewedHash !== report.envelope.scenario_sha256
  const currentIds = new Set(
    report.value.comparison.candidates.map(
      (candidate) => candidate.entry.transaction_id
    )
  )
  const unavailableSelected = selected.some((id) => !currentIds.has(id))
  const [error, setError] = useState(""),
    save = useCreateCaseworkEntry(report.value.case_id)
  const submit = () => {
    try {
      if (recalculated || unavailableSelected)
        throw Error(
          "Review the recalculated comparison and its selected payments before saving."
        )
      if (decision !== "agree" && decision !== "disagree")
        throw Error("Choose your response to the proposal.")
      const note = claimReviewNote(report, decision, reason, selected)
      setError("")
      save.mutate(note, { onSuccess: clearDraft })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review could not be prepared.")
    }
  }
  return (
    <section
      aria-label="Review the claim comparison"
      className="space-y-3 rounded border p-3"
    >
      <h4 className="font-semibold">Record your conclusion</h4>
      <p>
        Save a Workspace note with the quotation, your explanation and the
        payments you select below. The original claim and payments stay
        unchanged.
      </p>
      {!save.data && (
        <p className="text-sm text-muted-foreground">
          Your response and explanation are kept in this browser tab for these
          exact claim details. Save the review to share it with the case.
        </p>
      )}
      {recalculated && !save.data && (
        <div role="alert" className="rounded border p-3 space-y-2">
          <p>
            This comparison has been recalculated. Your response is retained.
            Check the current results before continuing.
          </p>
          <Button
            onClick={() =>
              setDraft((current) => ({
                ...current,
                reviewedHash: report.envelope.scenario_sha256,
              }))
            }
          >
            Use recalculated comparison
          </Button>
        </div>
      )}
      {unavailableSelected && !save.data && (
        <div role="alert" className="rounded border p-3 space-y-2">
          <p>
            Some selected payments are no longer in this comparison. Inspect the
            current results and choose the supporting payments again.
          </p>
          <Button
            onClick={() =>
              setDraft((current) => ({
                ...current,
                selected: current.selected.filter((id) => currentIds.has(id)),
              }))
            }
          >
            Remove unavailable selections
          </Button>
        </div>
      )}
      {save.data ? (
        <p role="status">
          Comparison review saved in Workspace.{" "}
          <a
            className="underline"
            href={`/cases/${encodeURIComponent(report.value.case_id)}/workspace`}
          >
            Open Workspace
          </a>
        </p>
      ) : (
        <fieldset
          disabled={save.isPending || save.isError}
          className="space-y-3"
        >
          <label className="block">
            Your response
            <select
              aria-label="Claim proposal response"
              value={decision}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  decision: e.target.value,
                }))
              }
              className="ml-2 border bg-background p-2"
            >
              <option value="">Choose a response</option>
              <option value="agree">Agree with the comparison</option>
              <option value="disagree">Disagree with the comparison</option>
            </select>
          </label>
          <label className="block">
            Supporting payments (up to 20)
            <select
              multiple
              size={Math.min(
                6,
                Math.max(2, report.value.comparison.candidates.length)
              )}
              aria-label="Supporting claim comparison readings"
              value={selected}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  selected: Array.from(
                    e.target.selectedOptions,
                    (option) => option.value
                  ),
                }))
              }
              className="block w-full border bg-background p-2"
            >
              {orderClaimCandidates(report.value.comparison.candidates).map(
                (c) => (
                  <option
                    key={c.entry.transaction_id}
                    value={c.entry.transaction_id}
                  >
                    {c.entry.ordering_date} ·{" "}
                    {correctionMoney(
                      c.entry.amount.minor_units,
                      c.entry.amount.currency
                    )}{" "}
                    · {c.entry.description || "No description recorded"} ·{" "}
                    {claimVerdictLabel(c.verdict)}
                  </option>
                )
              )}
            </select>
          </label>
          {selected.length > 20 && (
            <p role="alert">Select at most 20 payments for this review note.</p>
          )}
          <label className="block">
            Reason for your response
            <textarea
              aria-label="Claim review reason"
              maxLength={4096}
              value={reason}
              onChange={(e) =>
                setDraft((current) => ({ ...current, reason: e.target.value }))
              }
              className="block w-full border bg-background p-2"
            />
          </label>
          <Button
            disabled={
              !decision ||
              !reason.trim() ||
              selected.length > 20 ||
              recalculated ||
              unavailableSelected
            }
            onClick={submit}
          >
            {save.isPending ? "Saving…" : "Save claim review with sources"}
          </Button>
        </fieldset>
      )}
      {error && <p role="alert">{error}</p>}
      {save.isError && (
        <p role="alert">
          {save.error.message} Check Workspace before retrying, in case the
          response was lost after saving.
        </p>
      )}
    </section>
  )
}

export function ClaimComparisonDecision(
  props: Parameters<typeof ClaimComparisonDecisionForm>[0]
) {
  const { canEdit } = useFinancialAccess()
  return canEdit ? <ClaimComparisonDecisionForm {...props} /> : null
}
