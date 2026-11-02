import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { dossiersAPI } from "@/features/dossiers/api"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { liveCollectClient, type CollectLink } from "@/features/phones/collect.api"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { patternAPI, type Snapshot, type SnapshotRequest } from "../api"
import { errorWords } from "../lanes-lib"

/**
 * Collecting from Patterns and Lanes (07 section 6; CO-1 cells "Patterns" and "Lanes"). A pattern view is kept by
 * freezing it on the server ("Keep this result"); the frozen result is then added with the shared Add to… menu, or
 * to an interview. A statement check is added the same way under its own link type.
 */
export function CollectBar({ caseId, links, noun, origin }: { caseId: string; links: CollectLink[]; noun: string; origin: string }) {
  const t = useCollectTargets(caseId)
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" aria-label="Collect this">
      <AddToMenu caseId={caseId} links={links} noun={noun} origin={origin} targets={t.targets} client={liveCollectClient} keys={false} />
      {links.length === 1 && <InterviewLink caseId={caseId} item={{ target_type: links[0].target_type, target_id: links[0].target_id }} />}
      {t.note && <span className="text-muted-foreground">{t.note}</span>}
      {!!t.error && <span role="alert" className="text-destructive">{errorWords(t.error)}</span>}
    </div>
  )
}

/** Freeze what a view shows, then offer Add to… for the frozen result. */
export function KeepResult({ caseId, request, origin }: { caseId: string; request: SnapshotRequest; origin: string }) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const key = JSON.stringify(request)
  const [keptFor, setKeptFor] = useState<string | null>(null)
  async function keep() {
    setBusy(true); setErr(null)
    try { setSnap(await patternAPI.freeze(caseId, request)); setKeptFor(key) } catch (e) { setErr(errorWords(e)) } finally { setBusy(false) }
  }
  const current = snap && keptFor === key ? snap : null
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {!current && <Button size="sm" variant="outline" disabled={busy} onClick={keep}>{busy ? "Keeping…" : "Keep this result"}</Button>}
      {current && (
        <>
          <span>Kept: {current.label}, {current.record_count.toLocaleString("en-US")} records behind it.</span>
          <CollectBar caseId={caseId} noun="result" origin={origin}
            links={[{ target_type: "phone_analysis", target_id: current.id, label: current.label, source_anchor: {} }]} />
        </>
      )}
      {err && <span role="alert" className="text-destructive">{err}</span>}
    </div>
  )
}

/** Add one item (a statement check or a kept result) to an interview on a dossier, keeping the interview's others. */
export function InterviewLink({ caseId, item }: { caseId: string; item: { target_type: string; target_id: string } }) {
  const [open, setOpen] = useState(false)
  const [dossierId, setDossierId] = useState("")
  const [interviewId, setInterviewId] = useState("")
  const [reply, setReply] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const dossiers = useQuery({ queryKey: ["collect-targets", "dossiers", caseId], queryFn: () => dossiersAPI.list({ caseId, limit: 200 }), enabled: open && !!caseId })
  const dossier = useQuery({ queryKey: ["dossier", dossierId], queryFn: () => dossiersAPI.get(dossierId), enabled: !!dossierId })
  const interviews = dossier.data?.interviews || []
  if (!open) return <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>Add to an interview</Button>
  async function add() {
    setErr(null); setReply(null)
    try {
      const r = await patternAPI.addToInterview(dossierId, interviewId, item)
      setReply(r.added ? "Added to the interview's evidence." : "Already in the interview's evidence.")
    } catch (e) { setErr(errorWords(e)) }
  }
  return (
    <span className="flex flex-wrap items-center gap-1" role="group" aria-label="Add to an interview">
      <select aria-label="Dossier" value={dossierId} onChange={(e) => { setDossierId(e.target.value); setInterviewId("") }} className="rounded border bg-background px-1 py-0.5">
        <option value="">Choose a dossier{dossiers.data ? ` (${dossiers.data.total.toLocaleString("en-US")})` : ""}</option>
        {(dossiers.data?.dossiers || []).map((d) => <option key={d.id} value={d.id}>{d.display_name || d.display_name_snapshot}</option>)}
      </select>
      {dossiers.data && dossiers.data.total > dossiers.data.dossiers.length && <span>Showing {dossiers.data.dossiers.length.toLocaleString("en-US")} of {dossiers.data.total.toLocaleString("en-US")}.</span>}
      {dossierId && (
        <select aria-label="Interview" value={interviewId} onChange={(e) => setInterviewId(e.target.value)} className="rounded border bg-background px-1 py-0.5">
          <option value="">{interviews.length ? `Choose an interview (${interviews.length.toLocaleString("en-US")})` : "This dossier has no interviews"}</option>
          {interviews.map((i) => <option key={i.id} value={i.id}>{i.date_value || (i.interview_date || "").slice(0, 10) || "Undated"} · {i.status}</option>)}
        </select>
      )}
      <Button size="sm" disabled={!interviewId} onClick={add}>Add</Button>
      {reply && <span aria-live="polite">{reply}</span>}
      {err && <span role="alert" className="text-destructive">{err}</span>}
    </span>
  )
}
