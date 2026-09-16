import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import type { CaseworkLinkInput } from "@/features/workspace/casework-api"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { useFinancialDraft } from "../stores/financial-drafts"

function SavePaymentSelectionForm({
  caseId,
  ids,
  analysis,
  extraLinks = [],
  onReviewSelection,
}: {
  caseId: string
  ids: string[]
  analysis?: { kind: string; summary: string; details: Record<string, unknown> }
  extraLinks?: CaseworkLinkInput[]
  onReviewSelection?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [checked, setChecked] = useState(0)
  const [draft, setDraft, clear] = useFinancialDraft(
    caseId,
    analysis ? `analysis-note:${analysis.kind}` : "payment-selection-note",
    { title: "", body: "" }
  )
  const create = useCreateCaseworkEntry(caseId)
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!ids.length || new Set(ids).size !== ids.length)
        throw Error("Choose distinct payments before saving this selection.")
      setChecked(0)
      const links = new Map<string, CaseworkLinkInput>()
      for (let offset = 0; offset < ids.length; offset += 500) {
        const sources = await readSelectedPayments(
          caseId,
          ids.slice(offset, offset + 500)
        )
        for (const data of sources) {
          if (
            data.ledger_status !== "admitted" ||
            data.superseded_by_id !== null
          )
            throw Error(
              `${data.transaction.description || data.ref_id} (${data.transaction.ordering_date}) changed or is no longer included. Review your selected payments before saving.`
            )
        }
        setChecked(offset + sources.length)
        for (const source of sources) {
          const link = links.get(source.evidence_file_id) ?? {
            target_type: "evidence",
            target_id: source.evidence_file_id,
            target_label: source.filename,
            relationship: "context",
            source_anchor: {
              financial_transaction_ids: [],
              financial_ref_ids: [],
            },
            metadata: {
              schema: "loupe.financial.payment_selection/1",
              transactions: [],
            },
          }
          ;(link.source_anchor!.financial_transaction_ids as string[]).push(
            source.transaction_id
          )
          ;(link.source_anchor!.financial_ref_ids as string[]).push(
            source.ref_id
          )
          ;(link.metadata!.transactions as unknown[]).push(source.transaction)
          links.set(source.evidence_file_id, link)
        }
      }
      const savedLinks = [...links.values()]
      if (analysis && savedLinks[0])
        savedLinks[0].metadata = { ...savedLinks[0].metadata, analysis }
      if (
        new TextEncoder().encode(JSON.stringify(savedLinks)).length >
        32 * 1024 * 1024
      )
        throw Error(
          "The selected payment details exceed 32 MB. Save a smaller selection. Your selection and note are retained."
        )
      const entry = await create.mutateAsync({
        entry_type: "note",
        title: draft.title.trim(),
        body: draft.body.trim(),
        tags: [
          "financial",
          "payment-selection",
          ...(analysis ? [analysis.kind] : []),
        ],
        links: [...savedLinks, ...extraLinks],
      })
      if (entry.case_id !== caseId)
        throw Error(
          "The saved result did not match this case. Check Findings before trying again."
        )
      return entry
    },
    onSuccess: () => clear(),
  })
  return (
    <section className="space-y-3" aria-label="Save selected payments">
      <Button
        disabled={!ids.length}
        onClick={() => {
          setOpen(true)
          save.reset()
        }}
      >
        {analysis
          ? "Save this analysis with a note"
          : "Save selection with a note"}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!save.isPending) setOpen(value)
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Save selected payments</DialogTitle>
            <DialogDescription>
              Save these {ids.length} payments with a name and your observation.
              Reopen them from Findings or Workspace.
            </DialogDescription>
          </DialogHeader>
          {analysis && (
            <p className="text-sm rounded border p-3">{analysis.summary}</p>
          )}
          {save.isSuccess ? (
            <p role="status">
              Selection saved.{" "}
              <a
                className="underline"
                href={`/cases/${caseId}/workspace?view=casework&entry=${save.data.id}`}
              >
                Open saved note
              </a>
            </p>
          ) : (
            <fieldset disabled={save.isPending} className="space-y-3">
              <label className="block">
                Name for this selection
                <input
                  className="block w-full rounded border bg-background p-2"
                  value={draft.title}
                  maxLength={255}
                  onChange={(e) =>
                    setDraft({ ...draft, title: e.target.value })
                  }
                />
              </label>
              <label className="block">
                What did you notice?
                <textarea
                  aria-label="What did you notice?"
                  className="block w-full rounded border bg-background p-2 min-h-24"
                  value={draft.body}
                  maxLength={8000}
                  onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                />
              </label>
              <p className="text-xs text-muted-foreground">
                Unfinished text is kept in this browser tab until you save.
              </p>
              <Button
                disabled={
                  !draft.title.trim() ||
                  !draft.body.trim() ||
                  save.isPending ||
                  save.isError
                }
                onClick={() => save.mutate()}
              >
                {save.isPending
                  ? `Checking ${checked} of ${ids.length} payments and saving…`
                  : "Save payments and note"}
              </Button>
              {save.isError && (
                <p role="alert">
                  {save.error.message} Your draft is retained. Check Findings
                  before retrying.
                  {onReviewSelection && (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setOpen(false)
                        onReviewSelection()
                      }}
                    >
                      Review selected payments
                    </Button>
                  )}
                </p>
              )}
            </fieldset>
          )}
          <Button
            variant="outline"
            disabled={save.isPending}
            onClick={() => setOpen(false)}
          >
            Close
          </Button>
        </DialogContent>
      </Dialog>
    </section>
  )
}

export function SavePaymentSelection(
  props: Parameters<typeof SavePaymentSelectionForm>[0]
) {
  const { canEdit } = useFinancialAccess()
  return canEdit ? <SavePaymentSelectionForm {...props} /> : null
}
