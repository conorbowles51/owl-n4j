import { sha256 } from "@noble/hashes/sha2.js"
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import {
  useCreateCaseworkEntry,
  useUpdateCaseworkEntry,
} from "@/features/workspace/hooks/use-casework"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"
import {
  captureFindingPayments,
  emptyFinding,
  findingBody,
  findingDraft,
  findingTags,
  findingPaymentIds,
  type InvestigatorFindingDraft,
} from "../lib/investigator-finding"
import { SelectedPaymentsReview } from "./SelectedPaymentsReview"

export function InvestigatorFindingEditor({
  caseId,
  ids = [],
  entry,
  initial,
  onClose,
}: {
  caseId: string
  ids?: string[]
  entry?: CaseworkEntry
  initial?: Partial<InvestigatorFindingDraft>
  onClose: () => void
}) {
  const { canEdit } = useFinancialAccess()
  const selectionKey = Array.from(
    sha256(new TextEncoder().encode([...new Set(ids)].sort().join("\n"))),
    (byte) => byte.toString(16).padStart(2, "0")
  ).join("")
  const [draft, setDraft, clear] = useFinancialDraft<InvestigatorFindingDraft>(
    caseId,
    entry
      ? `finding-edit:${entry.id}:${entry.version}`
      : `finding-compose:${selectionKey}:${initial?.kind || "question"}:${initial?.title || "new"}`,
    entry ? findingDraft(entry) : { ...emptyFinding, ...initial }
  )
  const [review, setReview] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const create = useCreateCaseworkEntry(caseId)
  const update = useUpdateCaseworkEntry(caseId)
  const [attached, setAttached] = useState(() => [
    ...new Set(entry ? findingPaymentIds(entry) : ids),
  ])
  const change = (values: Partial<InvestigatorFindingDraft>) =>
    setDraft((current) => ({ ...current, ...values }))
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!canEdit || !draft.title.trim() || !draft.explanation.trim())
        throw Error("Add a title and explanation before saving.")
      // Edits retain the original cited versions. They must not recapture corrected payments silently.
      const links = entry
        ? entry.links
        : await captureFindingPayments(caseId, attached)
      const payload = {
        title: draft.title.trim(),
        body: findingBody(draft),
        tags: findingTags(draft, entry?.tags),
        links,
      }
      setUncertain(true)
      const result = entry
        ? await update.mutateAsync({
            entryId: entry.id,
            input: { ...payload, expected_version: entry.version },
          })
        : await create.mutateAsync({ ...payload, entry_type: "note" })
      if (result.case_id !== caseId)
        throw Error("The saved result did not match this case.")
      setUncertain(false)
      clear()
      return result
    },
  })
  return (
    <>
      <Dialog
        open={!review}
        onOpenChange={(open) => !open && !save.isPending && onClose()}
      >
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>
              {entry ? "Edit finding" : "Create finding"}
            </DialogTitle>
            <DialogDescription>
              Record your question, observation or conclusion with its
              supporting payments.
            </DialogDescription>
          </DialogHeader>
          {save.isSuccess ? (
            <div className="space-y-3" role="status">
              <p>
                Saved to this case. Colleagues with access can open it in
                Findings.
              </p>
              <Button
                onClick={() => {
                  useFinancialStore.getState().setMainView("findings")
                  onClose()
                }}
              >
                Open Findings
              </Button>
              <Button variant="outline" onClick={onClose}>
                Return to investigation
              </Button>
            </div>
          ) : (
            <fieldset
              disabled={!canEdit || save.isPending || uncertain}
              className="space-y-3"
            >
              <div className="grid grid-cols-2 gap-3">
                <label>
                  Type
                  <select
                    aria-label="Finding type"
                    className="block w-full rounded border bg-background p-2"
                    value={draft.kind}
                    onChange={(e) =>
                      change({
                        kind: e.target
                          .value as InvestigatorFindingDraft["kind"],
                      })
                    }
                  >
                    <option value="question">Question</option>
                    <option value="observation">Observation</option>
                    <option value="conclusion">Conclusion</option>
                  </select>
                </label>
                <label>
                  Progress
                  <select
                    aria-label="Progress"
                    className="block w-full rounded border bg-background p-2"
                    value={draft.progress}
                    onChange={(e) =>
                      change({
                        progress: e.target
                          .value as InvestigatorFindingDraft["progress"],
                      })
                    }
                  >
                    <option value="open">Open</option>
                    <option value="in-progress">In progress</option>
                    <option value="complete">Complete</option>
                  </select>
                </label>
              </div>
              <label className="block">
                Title
                <input
                  className="block w-full rounded border bg-background p-2"
                  maxLength={255}
                  aria-label="Title"
                  value={draft.title}
                  onChange={(e) => change({ title: e.target.value })}
                />
              </label>
              <label className="block">
                Explanation
                <textarea
                  className="block w-full rounded border bg-background p-2 min-h-28"
                  maxLength={6000}
                  aria-label="Explanation"
                  value={draft.explanation}
                  onChange={(e) => change({ explanation: e.target.value })}
                  placeholder="What do the records show? What remains unknown?"
                />
              </label>
              <label className="block">
                Next action
                <textarea
                  className="block w-full rounded border bg-background p-2"
                  maxLength={1500}
                  aria-label="Next action"
                  value={draft.nextAction}
                  onChange={(e) => change({ nextAction: e.target.value })}
                  placeholder="What needs to happen next?"
                />
              </label>
              <label className="block">
                Assigned to
                <input
                  className="block w-full rounded border bg-background p-2"
                  maxLength={200}
                  aria-label="Assigned to"
                  value={draft.owner}
                  onChange={(e) => change({ owner: e.target.value })}
                  placeholder="Name of the person following this up"
                />
              </label>
              <div className="rounded border bg-muted/20 p-3 flex flex-wrap items-center justify-between gap-2">
                <p>
                  {attached.length} supporting payments
                  {entry
                    ? " · original saved versions retained"
                    : " · original statement references included"}
                </p>
                {attached.length > 0 && (
                  <Button variant="outline" onClick={() => setReview(true)}>
                    Review attached payments
                  </Button>
                )}
              </div>
              <Button
                disabled={!draft.title.trim() || !draft.explanation.trim()}
                onClick={() => save.mutate()}
              >
                {save.isPending ? "Saving finding…" : "Save finding"}
              </Button>
            </fieldset>
          )}
          {save.isError && (
            <div role="alert" className="space-y-2">
              <p>{save.error.message}</p>
              {uncertain && (
                <>
                  <p>
                    The save result could not be confirmed. Your draft is
                    retained. Check Findings before saving another copy.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      useFinancialStore.getState().setMainView("findings")
                      onClose()
                    }}
                  >
                    Check Findings
                  </Button>
                </>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
      {review && (
        <SelectedPaymentsReview
          caseId={caseId}
          ids={attached}
          onRemove={
            entry
              ? undefined
              : (id) =>
                  setAttached((current) =>
                    current.filter((value) => value !== id)
                  )
          }
          onClose={() => setReview(false)}
        />
      )}
    </>
  )
}
