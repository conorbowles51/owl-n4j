import { useEffect, useMemo, useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { instantWords } from "@/features/phones/lib/time-words"
import { CollectBar } from "@/features/pattern/components/CollectBar"
import { patternAPI } from "@/features/pattern/api"
import type { AnalysisRun } from "./money-api"
import type { AnalysisClient, ApproachResult } from "./analysis-api"
import { anchorWords } from "./anchor-words"

/**
 * The shared results layout of every approach (05 section 3.9; 07 section 5; test AP-1), in this order: what it does,
 * Run with progress and Cancel, the coverage sentence from the run, results with the total under the filter, the
 * records behind a result, Add to…, and confirm or reject with a typed reason. Every result is labelled "Lead for
 * enquiry". Key dates (entered once per case, 07 section 5) are read here and placed beside each result's period.
 */
export interface KindTab { kind: string; label: string }

export interface RowWords { title: string; line?: string; when?: string }

export interface ApproachLayoutProps {
  caseId: string
  title: string
  whatItDoes: string
  client: AnalysisClient
  queryKey: string
  tabs: KindTab[]
  words: (r: ApproachResult) => RowWords
  collectLabel: (r: ApproachResult) => string
  origin: string
  testId: string
  /** Words for a direction code; the server's detail is used when absent. */
  emptyWords?: string
  extra?: ReactNode
}

function RunControl({ caseId, run, client, onRequested }: { caseId: string; run: AnalysisRun | null; client: AnalysisClient; onRequested: (r: AnalysisRun) => void }) {
  const [err, setErr] = useState<string | null>(null)
  const busy = run && (run.status === "queued" || run.status === "running")
  const request = useMutation({ mutationFn: () => client.request(caseId), onSuccess: onRequested, onError: (e) => setErr(String((e as Error).message || e)) })
  const cancel = useMutation({ mutationFn: () => client.cancel(caseId, run!.id), onSuccess: onRequested })
  const p = run?.progress || {}
  return (
    <section aria-label="Run" className="flex flex-wrap items-center gap-3 text-sm">
      <Button size="sm" onClick={() => request.mutate()} disabled={!!busy || request.isPending}>Run</Button>
      {busy && (
        <>
          <span role="status">{run!.status === "queued" ? "Waiting to start." : `Read ${(p.read ?? 0).toLocaleString("en-US")} of ${(p.total ?? 0).toLocaleString("en-US")} phones.`}</span>
          <Button size="sm" variant="outline" onClick={() => cancel.mutate()}>Cancel</Button>
        </>
      )}
      {run?.status === "completed" && run.finished_at && <span className="text-muted-foreground">Last run {instantWords(run.finished_at, "UTC")}.</span>}
      {run?.status === "failed" && <span role="alert" className="text-destructive">The last run stopped: {run.error}</span>}
      {err && <span role="alert" className="text-destructive">{err}</span>}
    </section>
  )
}

function Decide({ caseId, client, result, onDone }: { caseId: string; client: AnalysisClient; result: ApproachResult; onDone: () => void }) {
  const [reason, setReason] = useState("")
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({
    mutationFn: (d: "confirmed" | "rejected") => client.decide(caseId, result.id, d, reason.trim()),
    onSuccess: () => { setReason(""); onDone() },
    onError: (e) => setErr(String((e as Error).message || e)),
  })
  function go(d: "confirmed" | "rejected") {
    if (!reason.trim()) { setErr("Say why, in your own words."); return }
    setErr(null)
    m.mutate(d)
  }
  return (
    <div className="mt-2 space-y-1" aria-label="Confirm or reject">
      {result.decisions.map((d, i) => (
        <p key={i} className="text-xs">{d.decision === "confirmed" ? "Confirmed" : "Rejected"} by {d.by}: {d.reason}</p>
      ))}
      <Textarea aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} className="h-14 text-xs" placeholder="Why" />
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => go("confirmed")}>Confirm</Button>
        <Button size="sm" variant="outline" onClick={() => go("rejected")}>Reject</Button>
      </div>
      {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
    </div>
  )
}

function Behind({ caseId, client, queryKey, result, label, origin }: { caseId: string; client: AnalysisClient; queryKey: string; result: ApproachResult; label: string; origin: string }) {
  const q = useQuery({ queryKey: [queryKey, "detail", caseId, result.id], queryFn: () => client.detail(caseId, result.id) })
  if (!q.data) return <p className="text-xs text-muted-foreground">Loading the records behind it.</p>
  const recs = q.data.records.filter((r) => r.record_uid)
  const uniq = Array.from(new Map(recs.map((r) => [r.record_uid!, r])).values())
  return (
    <div className="space-y-1 text-xs" aria-label="Records behind it">
      <p>{uniq.length.toLocaleString("en-US")} {uniq.length === 1 ? "record" : "records"} behind it.</p>
      <ul className="max-h-48 space-y-0.5 overflow-auto">
        {uniq.map((r) => (
          <li key={r.record_uid!}>
            <Link className="underline" to={`/cases/${caseId}/records/${r.record_uid}`}>Open the phone record</Link>
            <span className="text-muted-foreground"> ({r.role.replace(/_/g, " ")})</span>
          </li>
        ))}
      </ul>
      <CollectBar caseId={caseId} noun="record" origin={origin}
        links={uniq.map((r) => ({ target_type: "phone_record", target_id: r.record_uid!, label, source_anchor: { kind: "phone_record", record_uid: r.record_uid } }))} />
    </div>
  )
}

function Row({ p, r, anchors, onChanged }: { p: ApproachLayoutProps; r: ApproachResult; anchors: { label: string; instant: string }[]; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  const w = p.words(r)
  const rel = anchors.map((a) => anchorWords(r.period_start, r.period_end, a.instant, a.label)).filter(Boolean) as string[]
  return (
    <li className="rounded border p-2 text-sm" data-testid={p.testId}>
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="rounded bg-muted px-1 text-xs">{r.label}</span>
        <button className="font-medium underline-offset-2 hover:underline" onClick={() => setOpen(!open)} aria-expanded={open}>{w.title}</button>
        {w.when && <span className="text-xs text-muted-foreground">{w.when}</span>}
        {r.decision && <span className="text-xs">{r.decision === "confirmed" ? "Confirmed" : "Rejected"}</span>}
      </div>
      {w.line && <p className="text-xs">{w.line}</p>}
      {rel.length > 0 && <p className="text-xs" aria-label="Against key dates">{rel.join(". ")}.</p>}
      {open && (
        <div className="mt-2 space-y-2">
          {r.directions.supports.length > 0 && (
            <ul className="list-disc pl-4 text-xs" aria-label="What supports it">{r.directions.supports.map((d, i) => <li key={i}>{d.detail}</li>)}</ul>
          )}
          {r.directions.undercuts.length > 0 && (
            <ul className="list-disc pl-4 text-xs" aria-label="What weakens it">{r.directions.undercuts.map((d, i) => <li key={i}>{d.detail}</li>)}</ul>
          )}
          <Behind caseId={p.caseId} client={p.client} queryKey={p.queryKey} result={r} label={p.collectLabel(r)} origin={p.origin} />
          <Decide caseId={p.caseId} client={p.client} result={r} onDone={onChanged} />
        </div>
      )}
    </li>
  )
}

export function ApproachLayout(p: ApproachLayoutProps) {
  const { caseId, client, queryKey } = p
  const qc = useQueryClient()
  const [run, setRun] = useState<AnalysisRun | null>(null)
  const [kind, setKind] = useState<string>(p.tabs[0]?.kind ?? "")
  const [offset, setOffset] = useState(0)
  const runs = useQuery({ queryKey: [queryKey, "runs", caseId], queryFn: () => client.runs(caseId), enabled: !!caseId })
  const coverage = useQuery({ queryKey: [queryKey, "coverage", caseId], queryFn: () => client.coverage(caseId), enabled: !!caseId })
  const keyDates = useQuery({ queryKey: ["pattern-key-dates", caseId, "date"], queryFn: () => patternAPI.keyDates(caseId, "date"), enabled: !!caseId })
  const anchors = useMemo(() => (keyDates.data?.items || []).filter((k) => k.instant_utc).map((k) => ({ label: k.label, instant: k.instant_utc! })), [keyDates.data])
  useEffect(() => {
    const items = runs.data?.items || []
    setRun((cur) => cur ?? items.find((r) => r.status === "completed") ?? items[0] ?? null)
  }, [runs.data])
  const active = run && (run.status === "queued" || run.status === "running")
  useEffect(() => {
    if (!active || !run) return
    const t = window.setInterval(async () => {
      const next = await client.run(caseId, run.id)
      setRun(next)
      if (next.status === "completed") qc.invalidateQueries({ queryKey: [queryKey, "results", caseId] })
    }, 2000)
    return () => window.clearInterval(t)
  }, [active, run, caseId, qc, client, queryKey])
  const done = run?.status === "completed" ? run : null
  const results = useQuery({
    queryKey: [queryKey, "results", caseId, done?.id, kind, offset],
    queryFn: () => client.results(caseId, done!.id, { kind, offset }),
    enabled: !!done,
  })
  const total = results.data?.total ?? 0
  const shown = results.data?.items.length ?? 0
  const byKind = (done?.counts as { by_kind?: Record<string, number> } | null)?.by_kind || {}
  return (
    <div className="space-y-4 p-4" data-testid={`${p.testId}-page`}>
      <h1 className="text-lg font-semibold">{p.title}</h1>
      <p data-part="what">{p.whatItDoes}</p>
      <div data-part="run"><RunControl caseId={caseId} run={run} client={client} onRequested={setRun} /></div>
      <p data-part="coverage" className="text-sm">{done?.coverage?.sentence || coverage.data?.sentence}</p>
      {p.extra}
      <section data-part="results" aria-label="Results" className="space-y-2">
        <div className="flex flex-wrap gap-2" role="tablist">
          {p.tabs.map((t) => (
            <Button key={t.kind} size="sm" role="tab" aria-selected={kind === t.kind} variant={kind === t.kind ? "primary" : "outline"}
              onClick={() => { setKind(t.kind); setOffset(0) }}>
              {t.label}{done ? ` (${(byKind[t.kind] ?? 0).toLocaleString("en-US")})` : ""}
            </Button>
          ))}
        </div>
        {!done && !active && <p className="text-sm">Not run yet in this case. Press Run.</p>}
        {done && (
          <p className="text-sm" data-testid={`${p.testId}-total`}>
            {total.toLocaleString("en-US")} {total === 1 ? "result" : "results"}
            {shown < total ? `, showing ${(offset + 1).toLocaleString("en-US")} to ${(offset + shown).toLocaleString("en-US")}` : ""}.
          </p>
        )}
        {done && total === 0 && p.emptyWords && <p className="text-sm text-muted-foreground">{p.emptyWords}</p>}
        <ul className="space-y-2">
          {(results.data?.items || []).map((r) => (
            <Row key={r.id} p={p} r={r} anchors={anchors} onChanged={() => qc.invalidateQueries({ queryKey: [queryKey, "results", caseId] })} />
          ))}
        </ul>
        {done && (offset > 0 || offset + shown < total) && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Earlier</Button>
            <Button size="sm" variant="outline" disabled={offset + shown >= total} onClick={() => setOffset(offset + 100)}>Later</Button>
          </div>
        )}
      </section>
    </div>
  )
}
