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
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import { useFinancialDraft } from "../stores/financial-drafts"
import { readSavedTrace, traceFindingLinks } from "../lib/saved-trace"
import { renderTraceReport, type VerifiedTrace } from "../lib/trace-report"
import { TraceReportDownload } from "./TraceReportDownload"

export function SaveTraceFinding({ trace }: { trace: VerifiedTrace }) {
  const caseId = trace.envelope.case_id
  const [draft, setDraft, clear] = useFinancialDraft(caseId, "trace-note", {
    title: "",
    body: "",
  })
  const create = useCreateCaseworkEntry(caseId)
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      const links = await traceFindingLinks(trace)
      const result = await create.mutateAsync({
        entry_type: "note",
        title: draft.title.trim(),
        body: draft.body.trim(),
        tags: ["financial", "saved-trace"],
        links,
      })
      if (result.case_id !== caseId)
        throw Error(
          "The saved result did not match this case. Check Findings before trying again."
        )
      return result
    },
    onSuccess: () => clear(),
  })
  return (
    <details className="rounded border p-3">
      <summary className="cursor-pointer font-medium">
        Save this calculation in Findings
      </summary>
      <p className="my-2">
        Keep this calculation, its assumptions and source references with your
        note. Reopening it shows these saved results, even if transactions are
        corrected later.
      </p>
      {save.isSuccess ? (
        <p role="status">Calculation saved in Findings.</p>
      ) : (
        <fieldset disabled={save.isPending} className="space-y-2">
          <label className="block">
            Name this calculation
            <input
              className="block w-full rounded border p-2"
              value={draft.title}
              maxLength={255}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </label>
          <label className="block">
            What does the calculation help you examine?
            <textarea
              className="block w-full rounded border p-2"
              value={draft.body}
              maxLength={8000}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            />
          </label>
          <Button
            disabled={
              !draft.title.trim() ||
              !draft.body.trim() ||
              save.isPending ||
              save.isError
            }
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Save calculation and note"}
          </Button>
          {save.isError && (
            <p role="alert">
              {save.error.message} Your text is retained. Check Findings before
              trying again.
            </p>
          )}
        </fieldset>
      )}
    </details>
  )
}

export function SavedTraceFinding({
  caseId,
  envelope,
}: {
  caseId: string
  envelope: unknown
}) {
  const [open, setOpen] = useState(false)
  const load = useMutation({
    retry: false,
    mutationFn: async () => {
      const trace = await readSavedTrace(envelope, caseId)
      return { trace, html: await renderTraceReport(trace) }
    },
  })
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true)
          load.mutate()
        }}
      >
        Open saved calculation
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-6xl max-h-[95vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Saved calculation</DialogTitle>
            <DialogDescription>
              These results use the assumptions and payments saved at the time.
              They have not been recalculated using later corrections.
            </DialogDescription>
          </DialogHeader>
          {load.isPending && <p role="status">Opening saved results…</p>}
          {load.isError && (
            <p role="alert">
              The saved calculation could not be opened. {load.error.message}
            </p>
          )}
          {load.data && (
            <>
              <TraceReportDownload trace={load.data.trace} />
              <iframe
                title="Saved tracing assumptions and results"
                sandbox=""
                srcDoc={load.data.html}
                className="w-full h-[65vh] border bg-white"
              />
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
