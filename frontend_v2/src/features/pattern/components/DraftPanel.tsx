import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { dossiersAPI } from "@/features/dossiers/api"
import { evidenceAPI } from "@/features/evidence/api"
import { workspaceAIAPI, type WorkspaceAIOutput } from "@/features/workspace-ai/api"
import { patternAPI, type Subject } from "../api"
import { errorWords } from "../lanes-lib"

/**
 * Draft with AI (07 J-9 step 1; 04 section 9.2): the model reads the chosen interviews of a person's dossier, or
 * documents of the case directly (a schedule, the other side's timeline), with full phone visibility, and proposes
 * claims. Nothing is a claim until a person accepts the drafts, and each
 * accepted draft still reads "Drafted by <model>, not confirmed" until it is confirmed. A failed call says so and
 * leaves typing claims by hand open.
 */
const FAILED = "AI drafting could not run. Enter claims by hand, or try again."

function modelOf(o: WorkspaceAIOutput) {
  const m = o.model_metadata || {}
  return String(m.model_id || m.model || m.provider || "the model")
}

export function DraftPanel({ caseId, subject, onAccepted }: { caseId: string; subject: Subject; onAccepted: () => void }) {
  const [dossierId, setDossierId] = useState("")
  const [chosen, setChosen] = useState<string[]>([])
  const [documents, setDocuments] = useState<string[]>([])
  const [out, setOut] = useState<WorkspaceAIOutput | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const dossiers = useQuery({ queryKey: ["collect-targets", "dossiers", caseId], queryFn: () => dossiersAPI.list({ caseId, limit: 200 }) })
  const dossier = useQuery({ queryKey: ["dossier", dossierId], queryFn: () => dossiersAPI.get(dossierId), enabled: !!dossierId })
  const interviews = dossier.data?.interviews || []
  const files = useQuery({ queryKey: ["draft-documents", caseId], queryFn: () => evidenceAPI.list(caseId, "processed"), enabled: !!dossierId })

  async function follow(id: string) {
    let o = await fetchAPI<WorkspaceAIOutput>(`/api/workspace/${encodeURIComponent(caseId)}/ai-outputs/${id}`)
    for (let i = 0; i < 90 && !["completed", "failed", "cancelled"].includes(o.job_status); i++) {
      setOut(o)
      await new Promise((ok) => setTimeout(ok, 2000))
      o = await fetchAPI<WorkspaceAIOutput>(`/api/workspace/${encodeURIComponent(caseId)}/ai-outputs/${id}`)
    }
    setOut(o)
    if (o.job_status === "failed" || o.job_status === "cancelled") setErr(FAILED)
    else if (o.job_status !== "completed") setErr("Drafting is still running after three minutes. It carries on; open this panel again to see it.")
  }

  async function draft() {
    setErr(null); setDone(null); setOut(null); setBusy("Drafting…")
    try {
      const r = await patternAPI.draft(caseId, { dossier_id: dossierId, subject, interview_ids: chosen, document_ids: documents })
      await follow(r.id)
    } catch (e) { setErr(`${FAILED} (${errorWords(e)})`) } finally { setBusy(null) }
  }

  async function retry() {
    if (!out) return
    setErr(null); setBusy("Drafting…")
    try { await workspaceAIAPI.retry(caseId, out.id); await follow(out.id) } catch (e) { setErr(`${FAILED} (${errorWords(e)})`) } finally { setBusy(null) }
  }

  async function accept() {
    if (!out) return
    setBusy("Adding the drafts…"); setErr(null)
    try {
      await workspaceAIAPI.accept(caseId, out.id)
      const n = (out.content.claims || []).length
      setDone(`${n.toLocaleString("en-US")} drafted claim${n === 1 ? "" : "s"} added. Each reads "Drafted by ${modelOf(out)}, not confirmed" until a person confirms it.`)
      onAccepted()
    } catch (e) { setErr(errorWords(e)) } finally { setBusy(null) }
  }

  const claims = (out?.job_status === "completed" ? out.content.claims : null) || null
  return (
    <details className="rounded border p-2">
      <summary className="cursor-pointer font-medium">Draft with AI</summary>
      <div className="mt-2 flex flex-col gap-2">
        <label className="flex flex-col">The person whose statement it is
          <select value={dossierId} onChange={(e) => { setDossierId(e.target.value); setChosen([]); setDocuments([]) }} className="rounded border bg-background px-2 py-1">
            <option value="">Choose a dossier{dossiers.data ? ` (${dossiers.data.total.toLocaleString("en-US")})` : ""}</option>
            {(dossiers.data?.dossiers || []).map((d) => <option key={d.id} value={d.id}>{d.display_name || d.display_name_snapshot}</option>)}
          </select>
        </label>
        {dossiers.data && dossiers.data.total > dossiers.data.dossiers.length && (
          <p className="text-xs">Showing {dossiers.data.dossiers.length.toLocaleString("en-US")} of {dossiers.data.total.toLocaleString("en-US")} dossiers, most recent first.</p>
        )}
        {dossierId && (
          <fieldset className="flex flex-col gap-1">
            <legend>Interviews to read ({interviews.length.toLocaleString("en-US")})</legend>
            {interviews.length === 0 && <p className="text-xs">This dossier has no interviews. Add one on the dossier, or enter claims by hand.</p>}
            {interviews.map((i) => (
              <label key={i.id} className="flex items-center gap-2">
                <input type="checkbox" disabled={documents.length > 0} checked={chosen.includes(i.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, i.id] : chosen.filter((x) => x !== i.id))} />
                {i.date_value || (i.interview_date || "").slice(0, 10) || "Undated"} · {i.status}
              </label>
            ))}
          </fieldset>
        )}
        {dossierId && (
          <label className="flex flex-col">Or documents to read directly, up to 20 ({(files.data?.length ?? 0).toLocaleString("en-US")} in this case)
            <select multiple disabled={chosen.length > 0} aria-label="Documents to read" value={documents} onChange={(e) => setDocuments(Array.from(e.target.selectedOptions, (o) => o.value).slice(0, 20))} className="h-24 rounded border bg-background px-2 py-1">
              {(files.data || []).map((f) => <option key={f.id} value={f.id}>{f.original_filename}</option>)}
            </select>
          </label>
        )}
        {(chosen.length > 0 || documents.length > 0) && (
          <p className="text-xs" data-testid="draft-one-kind">One draft reads interviews or documents, not both. Clear your choice to use the other.</p>
        )}
        <div className="flex gap-2">
          {documents.length > 0 && <Button size="sm" variant="outline" onClick={() => setDocuments([])}>Clear documents</Button>}
          <Button size="sm" disabled={!dossierId || (chosen.length === 0 && documents.length === 0) || !!busy} onClick={draft}>Draft with AI</Button>
          {err && out && <Button size="sm" variant="outline" disabled={!!busy} onClick={retry}>Try again</Button>}
        </div>
        {busy && <p aria-live="polite">{busy}{out ? ` (${out.job_status})` : ""}</p>}
        {err && <p role="alert" className="text-destructive">{err}</p>}
        {claims && (
          <div className="flex flex-col gap-1">
            <p className="font-medium">Drafted by {modelOf(out as WorkspaceAIOutput)}, not confirmed ({claims.length.toLocaleString("en-US")})</p>
            {out?.source_reading?.clipped && (
              <p role="status" data-testid="draft-clipped">
                Read {String(out.source_reading.chunks_read ?? out.source_reading.conversation_rows_read)} of {String(out.source_reading.chunks_available ?? out.source_reading.conversation_rows_available)} parts of the source, the bound for one draft. Draft the rest separately.
              </p>
            )}
            <ul className="flex flex-col gap-1">
              {claims.map((c, i) => {
                const x = c as unknown as { kind?: string; quote?: string; window_text?: string | null }
                return <li key={i}>{x.kind}: "{x.quote}"{x.window_text ? ` (time: ${x.window_text})` : ""}</li>
              })}
            </ul>
            {claims.length > 0 && !done && <Button size="sm" disabled={!!busy} onClick={accept}>Add these drafts</Button>}
          </div>
        )}
        {done && <p aria-live="polite">{done}</p>}
      </div>
    </details>
  )
}
