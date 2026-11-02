import { useMutation, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { createExport, describeExport, downloadExport, failureText, getExport, type StreamFilter } from "@/features/phones/api"

const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

/**
 * Export for counsel (03 section 12.2, 07 J-14): the scope in words with true totals, the reading state, then the
 * PDF drawn as a job with its progress, a failure that keeps the choices with a reference, and the finished file.
 */
export function ExportDialog(props: { caseId: string; filter: StreamFilter; words: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const { caseId, filter, words, open, onOpenChange } = props
  const [title, setTitle] = useState(words)
  const [exportId, setExportId] = useState<string | null>(null)
  const facts = useQuery({ queryKey: ["export-facts", caseId, filter], queryFn: () => describeExport(caseId, filter), enabled: open, retry: false })
  const start = useMutation({
    mutationFn: () => createExport(caseId, filter, { title: title.trim() || words, words }),
    onSuccess: (r) => setExportId(r.export_id),
  })
  const job = useQuery({
    queryKey: ["export", caseId, exportId],
    queryFn: () => getExport(caseId, exportId!),
    enabled: !!exportId,
    refetchInterval: (q) => (q.state.data && (q.state.data.state === "done" || q.state.data.state === "failed") ? false : 2000),
  })
  const save = useMutation({ mutationFn: () => downloadExport(caseId, exportId!, job.data?.file?.filename || "phone-messages.pdf") })
  const f = facts.data
  const kinds = f ? [plural(f.messages, "message", "messages"), ...(f.calls ? [plural(f.calls, "call", "calls")] : []), ...(f.other ? [plural(f.other, "other record", "other records")] : [])].join(" and ") : ""
  const running = job.data && (job.data.state === "queued" || job.data.state === "rendering")
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Export for counsel</DialogTitle>
          <DialogDescription>A PDF of exactly this list: every message complete, times as on screen. A character no bundled font can draw prints as [U+...] and is listed at the end.</DialogDescription>
        </DialogHeader>
        {facts.isLoading && <p role="status" className="text-sm">Counting what the export holds</p>}
        {facts.isError && <p role="alert" className="text-sm">{failureText(facts.error, "What the export holds could not be counted.")}</p>}
        {f && (
          <div className="flex flex-col gap-2 text-sm">
            <p>
              All {kinds}
              {words ? `, ${words}` : ""}, on {plural(f.phones, "phone", "phones")}, times in {f.zone}. {f.left_out}
            </p>
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
            <label className="flex flex-col gap-0.5 text-xs">
              <span className="font-medium">Title on the cover</span>
              <input className="rounded border bg-background px-2 py-1 text-sm" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
            </label>
          </div>
        )}
        {running && (
          <p role="status" className="text-sm">
            {job.data!.state === "queued" ? "Waiting to draw the PDF" : `Drawing the PDF: ${Math.round(job.data!.progress * 100)}% done`}
          </p>
        )}
        {job.data?.state === "failed" && <p role="alert" className="text-sm">{job.data.error}</p>}
        {start.isError && <p role="alert" className="text-sm">{failureText(start.error, "The export could not be started.")}</p>}
        {job.data?.state === "done" && (
          <p role="status" className="text-sm">
            The PDF is ready: {plural(Number(job.data.counts.total ?? 0), "row", "rows")}
            {Number(job.data.counts.missing_characters ?? 0) > 0 ? `, ${plural(Number(job.data.counts.missing_characters), "character", "characters")} printed as [U+...]` : ""}. SHA-256 {job.data.file?.sha256}
          </p>
        )}
        {save.isError && <p role="alert" className="text-sm">{failureText(save.error, "The file could not be saved.")}</p>}
        <DialogFooter>
          {job.data?.state === "done" ? (
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              Save the PDF
            </Button>
          ) : (
            <Button onClick={() => start.mutate()} disabled={!f || start.isPending || !!running}>
              {job.data?.state === "failed" ? "Try again" : "Export PDF"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
