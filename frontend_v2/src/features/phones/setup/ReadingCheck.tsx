import { useEffect, useMemo, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api-client"
import { trackUx } from "@/lib/ux-events"
import { ConfirmKindPanel } from "../review/ConfirmKindPanel"
import { readingsAPI, type CorrectionPreview, type ExampleKind, type Reading } from "../review/readings.api"
import { fmt } from "../ui/count-sentence"
import { loupeShows, reportLines } from "./example-words"
import { coverage } from "./setup-words"

/**
 * Check how the system read one phone (screen 6): one reading at a time as a plain sentence, ordered by records
 * affected, with what changes if it is wrong. Its examples sit side by side: the report's own fields, and what
 * Loupe makes of them. Looks right is refused until every kind of example has been on screen (RQ-2); Not right
 * needs a choice and the person's reason, and shows first what a correction would leave empty.
 */
function errorWords(e: unknown) {
  if (e instanceof ApiError) {
    const detail = (e.data as { detail?: unknown } | undefined)?.detail
    return typeof detail === "string" ? detail : e.message
  }
  return e instanceof Error ? e.message : String(e)
}

function ExamplePair({ k, zone, onSeen }: { k: ExampleKind; zone: string; onSeen: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // the kind counts as viewed once it has been on screen
    const el = ref.current
    if (!el || typeof IntersectionObserver === "undefined") return onSeen()
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { onSeen(); io.disconnect() } }, { threshold: 0.5 })
    io.observe(el)
    return () => io.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [k.id])
  return (
    <div ref={ref} data-kind={k.id} className="grid grid-cols-1 overflow-hidden rounded-lg border sm:grid-cols-2">
      <div className="border-b bg-muted/40 p-3 sm:border-b-0 sm:border-r">
        <p className="mb-1.5 text-xs text-muted-foreground">{k.label} · in the report · {fmt(k.count)} like it</p>
        <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground">{reportLines(k).join("\n")}</pre>
      </div>
      <div className="p-3">
        <p className="mb-1.5 text-xs text-muted-foreground">Loupe shows</p>
        <p className="text-[13px] leading-relaxed">{loupeShows(k, zone)}</p>
      </div>
    </div>
  )
}

export function ReadingCheck({ caseId, extraction, label, items, zone, initial }: { caseId: string; extraction: string; label: string; items: Reading[]; zone: string; initial?: string }) {
  const client = useQueryClient()
  const mine = useMemo(() => items.filter((r) => r.extraction_id === extraction), [items, extraction])
  const [id, setId] = useState<string | null>(initial ?? null)
  useEffect(() => {
    if (id && mine.some((r) => r.id === id)) return
    setId((mine.find((r) => r.status === "open") ?? mine[0])?.id ?? null)
  }, [mine, id])
  const index = Math.max(0, mine.findIndex((r) => r.id === id))
  const r = mine[index]
  const ex = useQuery({ queryKey: ["phone-reading-examples", caseId, r?.id], queryFn: () => readingsAPI.examples(caseId, r!.id), enabled: !!r })
  const [seen, setSeen] = useState<Record<string, string[]>>({})
  const [notRight, setNotRight] = useState(false)
  const [choice, setChoice] = useState<string | null>(null)
  const [reason, setReason] = useState("")
  const [scope, setScope] = useState<"this_phone" | "same_format">("this_phone")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [emptying, setEmptying] = useState<CorrectionPreview | null>(null)
  const [kindOpen, setKindOpen] = useState(false)
  const shownAt = useRef(performance.now())
  useEffect(() => {
    shownAt.current = performance.now()
    setNotRight(false); setChoice(null); setReason(""); setError(null); setEmptying(null); setKindOpen(false)
  }, [r?.id])
  const kinds = ex.data?.kinds ?? []
  const viewed = seen[r?.id ?? ""] ?? []
  const allSeen = kinds.length > 0 && kinds.every((k) => viewed.includes(k.id))
  const markSeen = (kid: string) => r && setSeen((v) => (v[r.id]?.includes(kid) ? v : { ...v, [r.id]: [...(v[r.id] ?? []), kid] }))
  const refresh = () => client.invalidateQueries({ queryKey: ["phone-readings", caseId] })
  const nextOpen = () => {
    const after = mine.slice(index + 1).find((x) => x.status === "open") ?? mine.find((x) => x.status === "open" && x.id !== r?.id)
    if (after) setId(after.id)
  }
  const track = (decision_kind: "confirm" | "correct" | "skip") =>
    trackUx(caseId, { event: "review_item", queue: "readings", decision_kind, ms: performance.now() - shownAt.current, examples_opened: viewed.length > 0, kinds_viewed: viewed.length, kinds_total: kinds.length })

  const confirm = async () => {
    if (!r || !allSeen || r.status !== "open" || busy) return
    setBusy(true); setError(null)
    try {
      await readingsAPI.confirm(caseId, r.id, { viewed, opened: viewed, expected_status: r.status })
      track("confirm")
      setSaved(`Saved under your name: reading ${index + 1} looks right.`)
      await refresh()
      nextOpen()
    } catch (e) {
      setError(errorWords(e)); await refresh()
    } finally { setBusy(false) }
  }
  const saveCorrection = async (agreed?: CorrectionPreview) => {
    if (!r || !choice || !reason.trim() || busy) return
    setBusy(true); setError(null)
    try {
      if (!agreed) {
        const pre = await readingsAPI.correctionPreview(caseId, r.id, { choice, scope })
        if (pre.records > 0) { setEmptying(pre); return }
      }
      await readingsAPI.correct(caseId, r.id, { choice, reason: reason.trim(), scope, expected_status: r.status, expected_empty: agreed?.records ?? 0 })
      track("correct")
      setSaved(`Saved under your name: reading ${index + 1} corrected. ${label} is read again; screens show the earlier reading until that finishes.`)
      setEmptying(null); setNotRight(false)
      await refresh()
      nextOpen()
    } catch (e) {
      setEmptying(null); setError(errorWords(e)); await refresh()
    } finally { setBusy(false) }
  }
  const skip = () => { track("skip"); nextOpen() }

  const cov = coverage(mine)
  if (mine.length === 0) return (
    <section id="check-readings" aria-label={`Check how the system read ${label}`} className="rounded-xl border bg-card p-5">
      <h2 className="text-[15px] font-semibold">Check how the system read {label}</h2>
      <p className="mt-1 text-[13px] text-muted-foreground">Nothing to check on this phone. Readings appear here when a phone is added or the system reads one differently.</p>
    </section>
  )
  const sameKind = r ? mine.filter((x) => x.status === "open" && x.part === r.part) : []
  return (
    <section id="check-readings" aria-label={`Check how the system read ${label}`} className="flex flex-col gap-4 rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold">Check how the system read {label}</h2>
          <p className="mt-1 text-[13px] text-muted-foreground">{fmt(cov.readings)} {cov.readings === 1 ? "reading" : "readings"}. Ordered by how many records each one affects, so the first few cover most of the phone.</p>
        </div>
        <div className="flex items-center gap-2.5 text-[13px]" role="status">
          <span className="font-mono">{fmt(cov.checked)} of {fmt(cov.readings)} checked</span>
          <div className="h-1.5 w-44 overflow-hidden rounded-full bg-muted" aria-hidden>
            <div className="h-full bg-status-success" style={{ width: `${cov.percent}%` }} />
          </div>
          <span>{cov.percent}% of records covered</span>
        </div>
      </div>
      {saved && <p role="status" className="text-[13px]">{saved}</p>}
      {r && (
        <div className="flex flex-wrap gap-5">
          <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Reading {index + 1} · affects {fmt(r.records)} {r.records === 1 ? "record" : "records"}</p>
            <p className="text-xl font-semibold leading-snug">{r.sentence}</p>
            {r.if_wrong && <p className="text-[13px] leading-relaxed text-muted-foreground">{r.if_wrong}</p>}
            {r.status === "open" ? (
              <p className="text-xs text-muted-foreground">Read by Loupe · not checked by a person yet.</p>
            ) : (
              <p role="status" className="text-[13px]">
                {r.status === "confirmed" ? "Confirmed" : "Corrected"} by {r.resolved_by}{r.reason ? `. Reason: ${r.reason}` : ""}.{r.status === "corrected" ? " The system's reading stays visible in the record history." : ""}
              </p>
            )}
            {r.earlier_decision && <p role={r.earlier_decision.needs_review ? "alert" : "status"} className="text-[13px]">{r.earlier_decision.words}</p>}
            <div className="mt-1 flex flex-wrap gap-2.5">
              <Button size="lg" variant="outline" className="h-11 border-status-success px-5 text-[14px]" onClick={() => void confirm()}
                disabled={!allSeen || r.status !== "open" || busy}
                disabledReason={r.status !== "open" ? "A person has already decided this reading." : !allSeen ? "Look at every example first; they are on the right." : undefined}>
                Looks right
              </Button>
              <Button size="lg" variant="outline" className="h-11 px-5 text-[14px]" onClick={() => setNotRight(true)} disabled={busy} aria-expanded={notRight}>Not right</Button>
              <Button size="lg" variant="ghost" className="h-11 px-5 text-[14px]" onClick={skip}>Skip for now</Button>
            </div>
            {r.status === "open" && sameKind.length > 1 && (
              <Button size="sm" variant="ghost" className="self-start px-1 text-[13px] text-foreground underline underline-offset-2" aria-expanded={kindOpen} onClick={() => setKindOpen((o) => !o)}>
                Looks right for all {fmt(sameKind.length)} readings like this on {label}…
              </Button>
            )}
            {kindOpen && <ConfirmKindPanel caseId={caseId} phone={label} rows={sameKind} note="" onClose={() => setKindOpen(false)} onDone={() => void refresh()} />}
            {notRight && (
              <fieldset className="flex flex-col gap-2 rounded-lg border p-3 text-[13px]">
                <legend className="px-1 font-medium">What is wrong?</legend>
                {r.choices.length === 0 ? (
                  <p>This reading cannot be changed for one phone yet. It can be changed for every case from the admin list.</p>
                ) : (
                  <div className="flex flex-wrap gap-2" role="group" aria-label="Corrections">
                    {r.choices.map((c) => (
                      <Button key={c.id} size="sm" variant={choice === c.id ? "secondary" : "outline"} aria-pressed={choice === c.id} onClick={() => setChoice(c.id)}>{c.label}</Button>
                    ))}
                  </div>
                )}
                {choice && (
                  <>
                    <label className="flex flex-col gap-1">Your reason (required)
                      <textarea className="rounded border bg-background px-2 py-1" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={4000} rows={2} />
                    </label>
                    <div role="radiogroup" aria-label="Applies to" className="flex flex-col gap-1">
                      <label><input type="radio" name="scope" checked={scope === "this_phone"} onChange={() => setScope("this_phone")} /> {label} in this case</label>
                      <label><input type="radio" name="scope" checked={scope === "same_format"} onChange={() => setScope("same_format")} /> {label} and the other phones in this case from the same kind of report</label>
                    </div>
                    <div>
                      <Button size="sm" onClick={() => void saveCorrection()} disabled={!reason.trim() || busy || !!emptying} disabledReason={busy ? undefined : emptying ? "Choose Continue or Cancel below first." : !reason.trim() ? "Type your reason to save the correction." : undefined}>Save correction</Button>
                    </div>
                    {emptying && (
                      <div role="alertdialog" aria-label="This correction would leave records empty" className="flex flex-col gap-2 rounded border border-status-review bg-status-review-soft p-2">
                        <p>{emptying.words}</p>
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => void saveCorrection(emptying)} disabled={busy}>Continue</Button>
                          <Button size="sm" variant="outline" onClick={() => setEmptying(null)} disabled={busy}>Cancel</Button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </fieldset>
            )}
            {error && <p role="alert" className="text-[13px]">{error}</p>}
          </div>
          <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">How it looks in the report, and what Loupe makes of it</p>
            {ex.isLoading ? (
              <p role="status" className="text-[13px]">Drawing examples from all {fmt(r.records)} records.</p>
            ) : ex.isError ? (
              <p role="alert" className="text-[13px]">The examples could not be loaded. {errorWords(ex.error)} <Button size="sm" variant="outline" onClick={() => void ex.refetch()}>Try again</Button></p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">One example of each kind among the {fmt(r.records)} records: {viewed.filter((v) => kinds.some((k) => k.id === v)).length} of {kinds.length} seen.{ex.data && ex.data.apps_not_shown > 0 ? ` ${fmt(ex.data.apps_not_shown)} less common apps are not shown as separate kinds.` : ""}</p>
                {kinds.map((k) => <ExamplePair key={`${r.id}-${k.id}`} k={k} zone={zone} onSeen={() => markSeen(k.id)} />)}
              </>
            )}
          </div>
        </div>
      )}
      <nav aria-label={`Readings of ${label}`} className="flex flex-wrap gap-1.5 border-t pt-3">
        {mine.map((x, i) => (
          <button key={x.id} type="button" onClick={() => setId(x.id)} aria-current={x.id === r?.id ? "true" : undefined}
            title={x.sentence}
            className="min-w-8 rounded border px-2 py-1 font-mono text-xs aria-[current=true]:border-foreground aria-[current=true]:bg-muted">
            {i + 1}{x.status === "open" ? "" : x.status === "confirmed" ? " ✓" : " ✎"}
            <span className="sr-only">{x.status === "open" ? ", not checked" : x.status === "confirmed" ? ", confirmed" : ", corrected"}</span>
          </button>
        ))}
      </nav>
    </section>
  )
}
