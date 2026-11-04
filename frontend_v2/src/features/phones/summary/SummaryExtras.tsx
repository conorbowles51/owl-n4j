import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { createExport, downloadExport, failureText, getExport, getExportHistory, getSinceLastLooked, type ExportState } from "../api"
import { fmt } from "../ui/count-sentence"

const LAST_LOOKED = (caseId: string, extraction: string) => `loupe.phone.lastLooked.${caseId}.${extraction}`

/**
 * Since you last looked (03 section 7.3, 07 J-15 step 3): counts per change kind after this viewer's previous visit
 * to this Phone summary. The time of the visit is kept in this browser only; the first visit says so.
 */
export function SinceYouLastLooked({ caseId, extraction }: { caseId: string; extraction: string }) {
  const [previous] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_LOOKED(caseId, extraction))
    } catch {
      return null
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(LAST_LOOKED(caseId, extraction), new Date().toISOString())
    } catch {
      /* storage refused: the next visit counts from the first one */
    }
  }, [caseId, extraction])
  const q = useQuery({
    queryKey: ["phone-since", caseId, extraction, previous],
    queryFn: () => getSinceLastLooked(caseId, extraction, previous!),
    enabled: !!previous,
  })
  if (!previous) return <p>This is your first visit to this phone's summary on this browser; changes are counted from now.</p>
  if (q.isLoading) return <p className="text-muted-foreground">Counting what changed</p>
  if (q.isError) return <p role="alert">{failureText(q.error, "What changed could not be counted.")}</p>
  const when = new Date(previous).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })
  return (
    <div>
      <p className="text-xs text-muted-foreground">Since your last visit on {when}:</p>
      {q.data?.nothing ? <p>Nothing has changed.</p> : (
        <ul className="flex flex-col gap-0.5">
          {q.data?.lines.map((l) => <li key={l}>{l}</li>)}
        </ul>
      )}
      {q.data?.counts.this_phone_read_again ? <p className="text-xs">This phone was read again in that time.</p> : null}
    </div>
  )
}

const SOURCE_WORDS: Record<string, string> = {
  stream: "Messages", timeline_lens: "Timeline phone lens", collection: "Collection", finding: "Finding", dossier: "Dossier",
  analysis_result: "Analysis result", statement_check: "Statement check", incident_window: "Incident window", phone_profile: "Phone summary",
}

/** Export history (03 section 7.3, 07 J-15): this case's phone exports that cover this phone, newest first, all of them. */
export function ExportHistory({ caseId, extraction }: { caseId: string; extraction: string }) {
  const q = useQuery({ queryKey: ["phone-export-history", caseId], queryFn: () => getExportHistory(caseId) })
  if (q.isLoading) return <p className="text-muted-foreground">Loading the export history</p>
  if (q.isError) return <p role="alert">{failureText(q.error, "The export history could not be loaded.")}</p>
  const mine = (q.data?.items ?? []).filter((e) => !e.phones || e.phones.length === 0 || e.phones.includes(extraction))
  if (mine.length === 0) return <p>Nothing has been exported from this phone yet.</p>
  return (
    <div>
      <p className="text-xs text-muted-foreground">
        {fmt(mine.length)} {mine.length === 1 ? "export covers" : "exports cover"} this phone.
      </p>
      <ul className="flex flex-col gap-0.5">
        {mine.map((e) => (
          <li key={e.export_id}>
            <ExportLine caseId={caseId} e={e} wholeCase={!e.phones || e.phones.length === 0} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function ExportLine({ caseId, e, wholeCase }: { caseId: string; e: ExportState; wholeCase: boolean }) {
  const [err, setErr] = useState<string | null>(null)
  const when = e.created_at ? new Date(e.created_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "time not recorded"
  const total = typeof e.counts.total === "number" ? ` ${fmt(e.counts.total)} ${e.source === "phone_profile" ? "records summarised" : "rows"}` : ""
  return (
    <span>
      {when}: {SOURCE_WORDS[e.source] ?? e.source}, {e.format.toUpperCase()}
      {e.title ? ` "${e.title}"` : ""}
      {wholeCase ? " (every phone in the case)" : ""}
      {e.state === "done" ? `,${total}` : e.state === "failed" ? `, failed: ${e.error ?? "no reason recorded"}` : `, ${e.state === "queued" ? "waiting to be drawn" : "being drawn"}`}{" "}
      {e.state === "done" && e.file?.filename && (
        <button type="button" className="underline underline-offset-2" onClick={() => downloadExport(caseId, e.export_id, e.file!.filename!).catch((x) => setErr(failureText(x, "The file could not be fetched.")))}>
          Download
        </button>
      )}
      {err && <span role="alert"> {err}</span>}
    </span>
  )
}

/** Export profile as PDF (03 section 7.3): drawn by the export jobs with the same renderer as the other exports. */
export function ExportProfile({ caseId, extraction, label }: { caseId: string; extraction: string; label: string }) {
  const qc = useQueryClient()
  const [id, setId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const job = useQuery({
    queryKey: ["phone-export", caseId, id],
    queryFn: () => getExport(caseId, id!),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && (q.state.data.state === "done" || q.state.data.state === "failed") ? false : 1500),
  })
  useEffect(() => {
    if (job.data?.state === "done" || job.data?.state === "failed") void qc.invalidateQueries({ queryKey: ["phone-export-history", caseId] })
  }, [job.data?.state, qc, caseId])
  const s = job.data
  return (
    <span className="flex items-center gap-2 text-xs">
      <Button
        size="sm"
        variant="outline"
        disabled={!!id && (!s || s.state === "queued" || s.state === "rendering")}
        onClick={() => {
          setErr(null)
          createExport(caseId, { case_id: caseId, phones: [extraction] } as never, { title: `Phone summary: ${label}` }, "pdf", "phone_profile")
            .then((r) => setId(r.export_id))
            .catch((x) => setErr(failureText(x, "The export could not be started.")))
        }}
      >
        Export profile as PDF
      </Button>
      {s && (s.state === "queued" || s.state === "rendering") && <span role="status">Drawing the PDF ({Math.round(s.progress * 100)}%)</span>}
      {s?.state === "done" && s.file?.filename && (
        <button type="button" className="underline underline-offset-2" onClick={() => downloadExport(caseId, s.export_id, s.file!.filename!).catch((x) => setErr(failureText(x, "The file could not be fetched.")))}>
          Download {s.file.filename}
        </button>
      )}
      {s?.state === "failed" && <span role="alert">The PDF could not be drawn: {s.error}</span>}
      {err && <span role="alert">{err}</span>}
    </span>
  )
}
