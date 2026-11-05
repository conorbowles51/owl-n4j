import { useMutation, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { createExport, describeExport, downloadExport, failureText, getExport, previewExport, type ExportSource, type StreamFilter } from "@/features/phones/api"
import { MachineTextPrompt } from "@/features/phones/media/MachineTextPrompt"

const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`
const rsmfMissing = (counts: Record<string, unknown>) =>
  Number((counts.rsmf as { attachments_not_included?: number } | undefined)?.attachments_not_included ?? 0)

/**
 * Export for counsel (03 section 12.2, 07 J-14): the scope in words with true totals, the reading state, then the
 * PDF drawn as a job with its progress, a failure that keeps the choices with a reference, and the finished file.
 */
export function ExportDialog(props: {
  caseId: string; filter: StreamFilter; words: string; open: boolean; onOpenChange: (v: boolean) => void
  /** "finding", "collection", "dossier"...: the frozen phone records of that source (07 XF-7, 6.4 item 14); `note`
   * says what of it is not in the export. "timeline_lens": `filter` is the Timeline phone lens filter. */
  source?: ExportSource; note?: string | null
}) {
  const { caseId, filter, words, open, onOpenChange, source = "stream", note } = props
  // the scope words read mid-sentence ("All 3 messages, the Case Timeline phone lens"); the cover title starts with a capital
  const [title, setTitle] = useState(words.charAt(0).toUpperCase() + words.slice(1))
  const [exportId, setExportId] = useState<string | null>(null)
  const [format, setFormat] = useState<"pdf" | "rsmf">("pdf")
  // 03 section 3.10: sensitive values stay out of an export unless this is ticked; the cover records the choice
  const [includeSensitive, setIncludeSensitive] = useState(false)
  const noun = format === "rsmf" ? "RSMF file" : "PDF"
  const [machineSettled, setMachineSettled] = useState(false)
  const facts = useQuery({ queryKey: ["export-facts", caseId, source, filter], queryFn: () => describeExport(caseId, filter, source), enabled: open, retry: false })
  const start = useMutation({
    mutationFn: () => createExport(caseId, filter, { title: title.trim() || words, words, ...(includeSensitive ? { include_sensitive: true } : {}) }, format, source),
    onSuccess: (r) => setExportId(r.export_id),
  })
  const job = useQuery({
    queryKey: ["export", caseId, exportId],
    queryFn: () => getExport(caseId, exportId!),
    enabled: !!exportId,
    refetchInterval: (q) => (q.state.data && (q.state.data.state === "done" || q.state.data.state === "failed") ? false : 2000),
  })
  // the first page exactly as the export draws it (07 J-14 step 4, test E-8); asked for, because it reads every row
  const preview = useMutation({ mutationFn: () => previewExport(caseId, filter, { title: title.trim() || words, words, ...(includeSensitive ? { include_sensitive: true } : {}) }, source) })
  const save = useMutation({ mutationFn: () => downloadExport(caseId, exportId!, job.data?.file?.filename || `phone-messages.${format}`) })
  const f = facts.data
  const kinds = f ? [plural(f.messages, "message", "messages"), ...(f.calls ? [plural(f.calls, "call", "calls")] : []), ...(f.other ? [plural(f.other, "other record", "other records")] : [])].join(" and ") : ""
  const running = job.data && (job.data.state === "queued" || job.data.state === "rendering")
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Export for counsel</DialogTitle>
          <DialogDescription>
            {format === "pdf"
              ? "A PDF of exactly this list: every message complete, times as on screen. A character no bundled font can draw prints as [U+...] and is listed at the end."
              : "One RSMF file of exactly this list for a review platform such as Relativity: the whole period in one conversation file, every message and attachment, times in UTC."}
          </DialogDescription>
        </DialogHeader>
        {facts.isLoading && <p role="status" className="text-sm">Counting what the export holds</p>}
        {facts.isError && <p role="alert" className="text-sm">{failureText(facts.error, "What the export holds could not be counted.")}</p>}
        {f && (
          <div className="flex flex-col gap-2 text-sm">
            <p>
              All {kinds}
              {words ? `, ${words}` : ""}, on {plural(f.phones, "phone", "phones")}, times in {f.zone}.{" "}
              {includeSensitive
                ? `Sensitive fields included: ${fmt(f.sensitive_values ?? 0)} ${(f.sensitive_values ?? 0) === 1 ? "value" : "values"} (saved passwords, card numbers and the like) will be printed.`
                : f.sensitive_values
                  ? `${f.left_out.replace(/\.$/, "")}: ${fmt(f.sensitive_values)} sensitive ${f.sensitive_values === 1 ? "value" : "values"} on these rows ${f.sensitive_values === 1 ? "is" : "are"} not printed.`
                  : f.left_out}
            </p>
            {f.hidden && <p>{f.hidden}</p>}
            {note && <p>{note}</p>}
            {f.unconfirmed > 0 ? (
              <p>
                {fmt(f.unconfirmed)} of these {fmt(f.total)} rows rely on readings not yet confirmed by a person.{" "}
                <Link className="underline underline-offset-2" to={`/cases/${encodeURIComponent(caseId)}/phone-review`}>
                  Review them first.
                </Link>
              </p>
            ) : (
              <p>Every row rests on readings confirmed by a person.</p>
            )}
            {f.limits.map((l) => (
              <p key={l.message} role="alert">
                {l.message}
              </p>
            ))}
            <fieldset className="flex gap-3 text-xs" disabled={!!exportId && !!running}>
              <legend className="sr-only">Format</legend>
              <label className="flex items-center gap-1">
                <input type="radio" name="export-format" checked={format === "pdf"} onChange={() => { setFormat("pdf"); setExportId(null) }} /> PDF
              </label>
              <label className="flex items-center gap-1">
                <input type="radio" name="export-format" checked={format === "rsmf"} onChange={() => { setFormat("rsmf"); setExportId(null) }} /> RSMF for a review platform
              </label>
            </fieldset>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={includeSensitive} disabled={!!exportId && !!running} onChange={(e) => { setIncludeSensitive(e.target.checked); setExportId(null) }} />
              Include sensitive fields
            </label>
            {format === "pdf" && f.machine_text && f.machine_text.unconfirmed > 0 && !exportId && (
              <MachineTextPrompt caseId={caseId} facts={f.machine_text} onSettled={setMachineSettled} />
            )}
            <label className="flex flex-col gap-0.5 text-xs">
              <span className="font-medium">{format === "pdf" ? "Title on the cover" : "Title"}</span>
              <input className="rounded border bg-background px-2 py-1 text-sm" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
            </label>
          </div>
        )}
        {f && format === "pdf" && (
          <div className="flex flex-col gap-1 text-xs">
            <Button size="sm" variant="outline" className="self-start" disabled={preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? "Drawing the first page" : preview.data ? "Draw the first page again" : "Preview the first page"}
            </Button>
            {preview.isError && <p role="alert">{failureText(preview.error, "The preview could not be drawn.")}</p>}
            {preview.data && (
              <figure className="flex flex-col gap-1">
                <img src={`data:image/png;base64,${preview.data.image}`} alt={`First page of the PDF: ${preview.data.text}`} className="max-h-96 w-fit rounded border object-contain object-top" data-testid="export-preview" />
                <figcaption className="text-muted-foreground">
                  Page 1, drawn as the export will draw it. The export id, the time and the page count are set when the PDF is made.
                  {includeSensitive ? " Sensitive fields are never drawn in a preview; the PDF will print them." : ""}
                </figcaption>
              </figure>
            )}
          </div>
        )}
        {running && (
          <p role="status" className="text-sm">
            {job.data!.state === "queued" ? `Waiting to make the ${noun}` : `Making the ${noun}: ${Math.round(job.data!.progress * 100)}% done`}
          </p>
        )}
        {job.data?.state === "failed" && <p role="alert" className="text-sm">{job.data.error}</p>}
        {start.isError && <p role="alert" className="text-sm">{failureText(start.error, "The export could not be started.")}</p>}
        {job.data?.state === "done" && (
          <p role="status" className="text-sm">
            The {noun} is ready: {plural(Number(job.data.counts.total ?? 0), "row", "rows")}
            {rsmfMissing(job.data.counts) > 0 ? `, ${plural(rsmfMissing(job.data.counts), "attachment", "attachments")} listed without the file; each says why` : ""}
            {Number(job.data.counts.missing_characters ?? 0) > 0 ? `, ${plural(Number(job.data.counts.missing_characters), "character", "characters")} printed as [U+...]` : ""}. SHA-256 {job.data.file?.sha256}
          </p>
        )}
        {save.isError && <p role="alert" className="text-sm">{failureText(save.error, "The file could not be saved.")}</p>}
        <DialogFooter>
          {job.data?.state === "done" ? (
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              Save the {noun}
            </Button>
          ) : (
            <Button onClick={() => start.mutate()} disabled={!f || start.isPending || !!running || (format === "pdf" && !exportId && !!f.machine_text?.unconfirmed && !machineSettled)}>
              {job.data?.state === "failed" ? "Try again" : format === "pdf" ? "Export PDF" : "Export RSMF"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
