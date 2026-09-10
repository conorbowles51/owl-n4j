import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import type { VerifiedClaimComparison } from "../lib/claim-comparison"
import { claimReviewNote } from "../lib/claim-review-note"
import { correctionMoney } from "../lib/correction-contract"
export function ClaimComparisonDecision({
  report,
}: {
  report: VerifiedClaimComparison
}) {
  const [decision, setDecision] = useState(""),
    [reason, setReason] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [error, setError] = useState(""),
    save = useCreateCaseworkEntry(report.value.case_id)
  const submit = () => {
    try {
      if (decision !== "agree" && decision !== "disagree")
        throw Error("Choose your response to the proposal.")
      const note = claimReviewNote(report, decision, reason, selected)
      setError("")
      save.mutate(note)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review could not be prepared.")
    }
  }
  return (
    <section
      aria-label="Review the claim comparison"
      className="space-y-3 rounded border p-3"
    >
      <h4 className="font-semibold">Record your response to this proposal</h4>
      <p>
        This creates a Workspace note with the quotation, selected source
        readings and your reasoning. It does not change the claim or ledger.
      </p>
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
              onChange={(e) => setDecision(e.target.value)}
              className="ml-2 border bg-background p-2"
            >
              <option value="">Choose a response</option>
              <option value="agree">Agree with the proposal</option>
              <option value="disagree">Disagree with the proposal</option>
            </select>
          </label>
          <label className="block">
            Supporting readings (up to20)
            <select
              multiple
              size={Math.min(
                6,
                Math.max(2, report.value.comparison.candidates.length)
              )}
              aria-label="Supporting claim comparison readings"
              value={selected}
              onChange={(e) =>
                setSelected(
                  Array.from(e.target.selectedOptions, (o) => o.value)
                )
              }
              className="block w-full border bg-background p-2"
            >
              {report.value.comparison.candidates.map((c) => (
                <option
                  key={c.entry.transaction_id}
                  value={c.entry.transaction_id}
                >
                  {c.verdict.replaceAll("_", " ")} ·{" "}
                  {correctionMoney(
                    c.entry.amount.minor_units,
                    c.entry.amount.currency
                  )}{" "}
                  · {c.entry.transaction_id}
                </option>
              ))}
            </select>
          </label>
          {selected.length > 20 && (
            <p role="alert">Select at most20 readings for this review note.</p>
          )}
          <label className="block">
            Reason for your response
            <textarea
              aria-label="Claim review reason"
              maxLength={4096}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="block w-full border bg-background p-2"
            />
          </label>
          <Button
            disabled={!decision || !reason.trim() || selected.length > 20}
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
