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
import { caseworkAPI } from "@/features/workspace/casework-api"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  emptyReportDraft,
  reportDraftName,
  prepareFinancialReport,
  reportSaveInput,
  MAX_REPORT_NOTES,
  type FinancialReportDraft,
} from "../lib/financial-report"
import { FinancialReportDocument } from "./FinancialReportDocument"

export function FinancialReportBuilder({
  caseId,
  caseTitle,
}: {
  caseId: string
  caseTitle: string
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useFinancialDraft<FinancialReportDraft>(
    caseId,
    reportDraftName,
    emptyReportDraft
  )
  const create = useCreateCaseworkEntry(caseId)
  const signature = JSON.stringify(draft)
  const preview = useMutation({
    retry: false,
    mutationFn: async () => {
      const notes = []
      if (!draft.selected.length || draft.selected.length > MAX_REPORT_NOTES)
        throw Error(`Choose between 1 and ${MAX_REPORT_NOTES} findings.`)
      for (const selected of draft.selected) {
        const note = await caseworkAPI.get(caseId, selected.id)
        if (
          note.id !== selected.id ||
          note.case_id !== caseId ||
          note.version !== selected.version
        )
          throw Error(
            "A selected note has changed. Use the latest selected notes, then preview the report again."
          )
        notes.push(note)
      }
      return {
        signature,
        report: await prepareFinancialReport({
          caseId,
          caseTitle,
          title: draft.title,
          introduction: draft.introduction,
          notes,
        }),
      }
    },
  })
  const latest = useMutation({
    retry: false,
    mutationFn: async () => {
      const selected = []
      for (const selection of draft.selected) {
        const note = await caseworkAPI.get(caseId, selection.id)
        if (
          note.id !== selection.id ||
          note.case_id !== caseId ||
          note.deleted_at
        )
          throw Error(
            "A selected note is no longer available. Remove it from the report."
          )
        selected.push({
          id: note.id,
          title: note.title || "Untitled note",
          version: note.version,
        })
      }
      return selected
    },
    onSuccess: (selected) => {
      setDraft((current) => ({ ...current, selected }))
      preview.reset()
    },
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!preview.data || preview.data.signature !== signature)
        throw Error("Preview the current selection before saving.")
      const result = await create.mutateAsync(
        reportSaveInput(preview.data.report)
      )
      if (result.case_id !== caseId)
        throw Error(
          "The saved response did not match this case. Check Reports before trying again."
        )
      return { entry: result, savedSignature: signature }
    },
    onSuccess: ({ savedSignature }) =>
      setDraft((current) =>
        JSON.stringify(current) === savedSignature ? emptyReportDraft : current
      ),
  })
  const busy = preview.isPending || latest.isPending || save.isPending
  const current =
    preview.data?.signature === signature ? preview.data.report : null
  return (
    <div className="space-y-2">
      <Button
        disabled={!draft.selected.length}
        onClick={() => {
          setOpen(true)
          save.reset()
        }}
      >
        Build report ({draft.selected.length})
      </Button>
      <p className="text-sm text-muted-foreground">
        Select Include in report on the notes below. You can choose notes across
        search results and pages, up to {MAX_REPORT_NOTES} per report.
      </p>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value)
        }}
      >
        <DialogContent className="sm:max-w-6xl max-h-[95vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Build a financial report</DialogTitle>
            <DialogDescription>
              Choose the order, write an introduction and preview the included
              findings before saving or downloading.
            </DialogDescription>
          </DialogHeader>
          {save.isSuccess ? (
            <p role="status">
              Report saved to this case. Open it from Findings or{" "}
              <a className="underline" href={`/cases/${caseId}/reports`}>
                Reports
              </a>
              . The original notes are unchanged.
            </p>
          ) : (
            <>
              <fieldset disabled={busy || save.isError} className="space-y-3">
                <label className="block">
                  Report title
                  <input
                    className="block w-full rounded border bg-background p-2"
                    maxLength={255}
                    value={draft.title}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        title: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="block">
                  Introduction
                  <textarea
                    className="block min-h-24 w-full rounded border bg-background p-2"
                    maxLength={8000}
                    value={draft.introduction}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        introduction: event.target.value,
                      }))
                    }
                  />
                </label>
                <ol className="space-y-2" aria-label="Report finding order">
                  {draft.selected.map((note, index) => (
                    <li
                      key={note.id}
                      className="flex flex-wrap items-center gap-2 rounded border p-2"
                    >
                      <span className="flex-1">
                        {index + 1}. {note.title} · version {note.version}
                      </span>
                      <Button
                        variant="outline"
                        disabled={index === 0}
                        aria-label={`Move ${note.title} earlier`}
                        onClick={() =>
                          setDraft((current) => {
                            const selected = [...current.selected]
                            ;[selected[index - 1], selected[index]] = [
                              selected[index],
                              selected[index - 1],
                            ]
                            return { ...current, selected }
                          })
                        }
                      >
                        Move up
                      </Button>
                      <Button
                        variant="outline"
                        disabled={index === draft.selected.length - 1}
                        aria-label={`Move ${note.title} later`}
                        onClick={() =>
                          setDraft((current) => {
                            const selected = [...current.selected]
                            ;[selected[index], selected[index + 1]] = [
                              selected[index + 1],
                              selected[index],
                            ]
                            return { ...current, selected }
                          })
                        }
                      >
                        Move down
                      </Button>
                      <Button
                        variant="outline"
                        aria-label={`Remove ${note.title} from report`}
                        onClick={() =>
                          setDraft((current) => ({
                            ...current,
                            selected: current.selected.filter(
                              (item) => item.id !== note.id
                            ),
                          }))
                        }
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ol>
                <p className="text-sm text-muted-foreground">
                  Your report title, introduction and selections are kept in
                  this browser tab until you save. Changing the report clears
                  its preview.
                </p>
                <Button
                  disabled={!draft.title.trim() || !draft.selected.length}
                  onClick={() => preview.mutate()}
                >
                  {preview.isPending ? "Preparing preview…" : "Preview report"}
                </Button>
              </fieldset>
              {preview.isError && (
                <div role="alert">
                  <p>{preview.error.message}</p>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => latest.mutate()}
                  >
                    Use latest selected notes
                  </Button>
                </div>
              )}
              {latest.isError && <p role="alert">{latest.error.message}</p>}
              {save.isError && (
                <p role="alert">
                  {save.error.message} Your draft is retained. Check Reports
                  before trying to save again.
                </p>
              )}
              {current && (
                <FinancialReportDocument
                  key={current.envelope.sha256}
                  report={current}
                  saveAction={
                    <Button
                      disabled={busy || save.isError}
                      onClick={() => save.mutate()}
                    >
                      {save.isPending
                        ? "Saving report…"
                        : "Save report to case"}
                    </Button>
                  }
                />
              )}
            </>
          )}
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => setOpen(false)}
          >
            Close report builder
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
