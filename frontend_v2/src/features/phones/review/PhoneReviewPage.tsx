import { useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/ui/page-header"
import { ApiError } from "@/lib/api-client"
import { installKeymap, register } from "@/lib/keymap"
import { trackUx } from "@/lib/ux-events"
import { fmt } from "../ui/count-sentence"
import { KeymapOverlay } from "../ui/KeymapOverlay"
import { ConfirmKindPanel } from "./ConfirmKindPanel"
import { ExampleView } from "./ExampleView"
import { IdentityLinkGroup } from "./IdentityLinkGroup"
import { PeopleSuggestions } from "./PeopleSuggestions"
import { ReadingRechecks } from "./ReadingRechecks"
import { identitiesAPI } from "./identities.api"
import { readingsAPI, type CorrectionPreview, type ExampleKind, type PhoneProgress, type Reading, type ReadingExamples } from "./readings.api"

/**
 * Needs a decision, readings group (02 sections 6.8 and 6.10; 07 J-8 and section 5). Each reading is one rule the
 * system applied on one phone, shown as a plain sentence and ordered by records affected. Examples are drawn from
 * the whole affected set, one per kind present; Looks right stays disabled until every kind has been viewed. A
 * confirmation records the standard reason; Not right offers plain choices and needs the person's own reason. The
 * decision applies to that phone in this case; screens show the earlier reading until the re-reading finishes.
 */
const ZONE = "UTC"
const ORIGIN = "Mapped by the system, not yet confirmed"

function dateWords(iso: string | null) {
  if (!iso) return ""
  return new Intl.DateTimeFormat("en-GB", { timeZone: ZONE, day: "numeric", month: "long", year: "numeric" }).format(new Date(iso))
}

function errorWords(e: unknown) {
  if (e instanceof ApiError) {
    const detail = (e.data as { detail?: unknown } | undefined)?.detail
    return typeof detail === "string" ? detail : e.message
  }
  return e instanceof Error ? e.message : String(e)
}

function ProgressLine({ p, records }: { p: PhoneProgress; records: number }) {
  if (p.state === "done") return null
  if (p.state === "waiting")
    return <p role="status" className="text-sm">Your correction is saved. Re-reading {p.phone} starts shortly. Screens show the earlier reading until this finishes.</p>
  const left = p.seconds_left != null ? `, about ${fmt(p.seconds_left)} s left` : ""
  return (
    <p role="status" className="text-sm">
      Re-reading {fmt(p.records_total || records)} records on {p.phone}: {fmt(p.records_done)} done{left}. Screens show the earlier reading until this finishes.
    </p>
  )
}

export function ReadingsGroup({ caseId }: { caseId: string }) {
  const client = useQueryClient()
  const queue = useQuery({ queryKey: ["phone-readings", caseId], queryFn: () => readingsAPI.list(caseId) })
  const items = useMemo(() => queue.data?.items ?? [], [queue.data])
  const [index, setIndex] = useState(0)
  // The list keeps readings already decided (in order, so the count reads true); the page opens on the first one
  // still needing a decision, once. After a decision it stays on that reading, which then shows who decided.
  // A link from the record panel (07 J-8b) names the reading: ?reading=<id>, and &answer=not-right opens the choices.
  const [linkParams] = useSearchParams()
  const [notRight, setNotRight] = useState(false)
  const linked = linkParams.get("reading")
  const placed = useRef(false)
  const openNotRightOn = useRef<string | null>(null)
  useEffect(() => {
    if (placed.current || items.length === 0) return
    placed.current = true
    const named = linked ? items.findIndex((x) => x.id === linked) : -1
    const first = named >= 0 ? named : items.findIndex((x) => x.status === "open")
    if (first > 0) setIndex(first)
    if (named >= 0 && linkParams.get("answer") === "not-right") openNotRightOn.current = items[named].id
  }, [items, linked, linkParams])
  const r: Reading | undefined = items[Math.min(index, Math.max(0, items.length - 1))]
  const ex = useQuery({
    queryKey: ["phone-reading-examples", caseId, r?.id],
    queryFn: () => readingsAPI.examples(caseId, r!.id),
    enabled: Boolean(r),
  })
  const [viewed, setViewed] = useState<Record<string, string[]>>({})
  const [open, setOpen] = useState<string | null>(null)
  const [choice, setChoice] = useState<string | null>(null)
  const [reason, setReason] = useState("")
  const [note, setNote] = useState("")
  const [scope, setScope] = useState<"this_phone" | "same_format">("this_phone")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [watching, setWatching] = useState<string | null>(null)
  const [emptying, setEmptying] = useState<CorrectionPreview | null>(null)
  const [kindOpen, setKindOpen] = useState(false)
  const progress = useQuery({
    queryKey: ["phone-reading-progress", caseId],
    queryFn: () => readingsAPI.progress(caseId),
    enabled: Boolean(watching),
    refetchInterval: watching ? 1000 : false,
  })
  const shownAt = useRef(performance.now())
  useEffect(() => {
    shownAt.current = performance.now()
    // A Not right link opens the choices once, on the reading it names; any other reading starts closed.
    // The first render still shows the first reading, so the mark stays until the named reading is on screen.
    const named = !!r?.id && openNotRightOn.current === r.id
    setNotRight(named)
    if (named) openNotRightOn.current = null
    setChoice(null)
    setReason("")
    setNote("")
    setError(null)
    setOpen(null)
    setEmptying(null)
    setKindOpen(false)
  }, [r?.id])
  const kinds = ex.data?.kinds ?? []
  const seen = viewed[r?.id ?? ""] ?? []
  const allSeen = kinds.length > 0 && kinds.every((k) => seen.includes(k.id))
  const watched = progress.data?.phones.find((p) => p.extraction_id === watching)
  useEffect(() => {
    if (watching && watched?.state === "done") {
      setWatching(null)
      void client.invalidateQueries({ queryKey: ["phone-readings", caseId] })
    }
  }, [watching, watched?.state, client, caseId])

  const refresh = () => client.invalidateQueries({ queryKey: ["phone-readings", caseId] })
  const view = (k: ExampleKind) => {
    setOpen((o) => (o === k.id ? null : k.id))
    if (r && !seen.includes(k.id)) setViewed((v) => ({ ...v, [r.id]: [...(v[r.id] ?? []), k.id] }))
  }
  const track = (decision_kind: "confirm" | "correct" | "skip") =>
    r && trackUx(caseId, { event: "review_item", queue: "readings", decision_kind, ms: performance.now() - shownAt.current,
      examples_opened: seen.length > 0, kinds_viewed: seen.length, kinds_total: kinds.length })
  const next = () => setIndex((i) => Math.min(items.length - 1, i + 1))
  const prev = () => setIndex((i) => Math.max(0, i - 1))
  const confirm = async () => {
    if (!r || !allSeen || r.status !== "open" || busy) return
    setBusy(true)
    setError(null)
    try {
      await readingsAPI.confirm(caseId, r.id, { viewed: seen, opened: seen, note: note.trim() || undefined, expected_status: r.status })
      track("confirm")
      await refresh()
    } catch (e) {
      setError(errorWords(e))
      await refresh()
    } finally {
      setBusy(false)
    }
  }
  // A correction that would leave something empty is shown first, with its true count; nothing is written until
  // Continue, and the server refuses if the count is no longer the one agreed to (07 J-8 failure state).
  const saveCorrection = async (agreed?: CorrectionPreview) => {
    if (!r || !choice || !reason.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      if (!agreed) {
        const seen = await readingsAPI.correctionPreview(caseId, r.id, { choice, scope })
        if (seen.records > 0) {
          setEmptying(seen)
          return
        }
      }
      await readingsAPI.correct(caseId, r.id, { choice, reason: reason.trim(), scope, note: note.trim() || undefined, expected_status: r.status, expected_empty: agreed?.records ?? 0 })
      track("correct")
      setEmptying(null)
      setNotRight(false)
      setWatching(r.extraction_id)
      await refresh()
    } catch (e) {
      setEmptying(null)
      setError(errorWords(e))
      await refresh()
    } finally {
      setBusy(false)
    }
  }
  const skip = () => {
    track("skip")
    next()
  }

  useEffect(
    () =>
      register("Needs a decision", [
        { key: "y", label: "Looks right", run: () => void confirm() },
        { key: "x", label: "Not right", run: () => setNotRight(true) },
        { key: "s", label: "Skip", run: skip },
        { key: "j", label: "Next reading", run: next },
        { key: "k", label: "Previous reading", run: prev },
      ]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [r?.id, r?.status, allSeen, busy, items.length, note]
  )

  if (queue.isLoading) return <p role="status" className="text-sm">Loading the readings to check.</p>
  if (queue.isError) return <p role="alert" className="text-sm">The readings could not be loaded. {errorWords(queue.error)} <Button size="sm" variant="outline" onClick={() => void queue.refetch()}>Try again</Button></p>
  if (!r) return <p className="text-sm">Nothing needs a decision. New items appear when a phone is added or a reading changes.</p>
  const checked = queue.data?.checked ?? 0
  // The rows of this kind on this phone that a person can still confirm: one rule part on one phone (UXD-58).
  const sameKind = items.filter((x) => x.status === "open" && x.extraction_id === r.extraction_id && x.part === r.part)
  return (
    <section aria-labelledby="readings-group" className="flex flex-col gap-3">
      <h2 id="readings-group" className="text-base font-semibold">Readings to check</h2>
      <p role="status" className="text-sm">{fmt(checked)} of {fmt(items.length)} checked. {fmt(queue.data?.open ?? 0)} are {ORIGIN.toLowerCase()}.</p>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <nav aria-label="Readings to check" className="max-h-[70vh] overflow-auto rounded border bg-card p-2 text-sm">
          <ol className="flex flex-col gap-1" aria-label={`${items.length} readings`}>
            {items.map((x, i) => (
              <li key={x.id}>
                <button type="button" aria-current={x.id === r.id ? "true" : undefined} onClick={() => setIndex(i)} className="w-full rounded px-1.5 py-1 text-left hover:bg-muted aria-[current=true]:bg-accent">
                  <span>{x.sentence}</span>
                  <span className="block text-xs text-muted-foreground">{x.status === "open" ? ORIGIN : x.status === "confirmed" ? `Confirmed by ${x.resolved_by}` : `Corrected by ${x.resolved_by}`}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <article aria-labelledby="reading-now" className="flex flex-col gap-3">
          <h3 id="reading-now" className="text-sm font-semibold">Reading {index + 1} of {items.length}</h3>
          <p className="text-base">This reading: {r.sentence}</p>
          {r.status === "open" && <p className="text-sm text-muted-foreground">{ORIGIN}.</p>}
          {r.status === "confirmed" && (
            <p role="status" className="text-sm">
              Confirmed by {r.resolved_by} on {dateWords(r.resolved_at)}. {r.reason_kind === "standard" ? "Standard reason" : "Reason"}: {r.reason}.{r.note ? ` Note: ${r.note}` : ""}
            </p>
          )}
          {r.status === "corrected" && (
            <p role="status" className="text-sm">
              Corrected by {r.resolved_by} on {dateWords(r.resolved_at)}. Reason: {r.reason}. The system's reading stays visible in the record history.
            </p>
          )}
          {watching === r.extraction_id && watched && <ProgressLine p={watched} records={r.records} />}
          {ex.isLoading ? (
            <p role="status" className="text-sm">Drawing examples from all {fmt(r.records)} records.</p>
          ) : ex.isError ? (
            <p role="alert" className="text-sm">The examples could not be loaded. {errorWords(ex.error)}</p>
          ) : (
            <Examples ex={ex.data!} seen={seen} open={open} onView={view} records={r.records} />
          )}
          <label className="flex flex-col gap-1 text-sm">
            Note (optional)
            <input className="rounded border bg-background px-2 py-1" value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => void confirm()} disabled={!allSeen || r.status !== "open" || busy} title={!allSeen ? "Open every kind of example first" : undefined}>
              Looks right <kbd className="ml-1 text-xs">y</kbd>
            </Button>
            <Button variant="outline" onClick={() => setNotRight(true)} disabled={busy}>
              Not right <kbd className="ml-1 text-xs">x</kbd>
            </Button>
            <Button variant="ghost" onClick={skip}>
              Skip <kbd className="ml-1 text-xs">s</kbd>
            </Button>
            {r.status === "open" && sameKind.length > 1 && (
              <Button variant="outline" aria-expanded={kindOpen} onClick={() => setKindOpen((o) => !o)}>
                Looks right for all {fmt(sameKind.length)} rows of this kind on this phone…
              </Button>
            )}
            {!allSeen && r.status === "open" && <span className="text-sm text-muted-foreground">Looks right is available once every kind of example has been opened.</span>}
          </div>
          {kindOpen && (
            <ConfirmKindPanel caseId={caseId} phone={r.phone} rows={sameKind} note={note}
              onClose={() => setKindOpen(false)} onDone={() => void refresh()} />
          )}
          {notRight && (
            <fieldset className="flex flex-col gap-2 rounded border p-2 text-sm">
              <legend className="font-medium">What is wrong?</legend>
              {r.choices.length === 0 ? (
                <p>This reading cannot be changed for one phone yet. It can be changed for every case from the admin list.</p>
              ) : (
                <div className="flex flex-wrap gap-2" role="group" aria-label="Corrections">
                  {r.choices.map((c) => (
                    <Button key={c.id} size="sm" variant={choice === c.id ? "primary" : "outline"} aria-pressed={choice === c.id} onClick={() => setChoice(c.id)}>
                      {c.label}
                    </Button>
                  ))}
                </div>
              )}
              {choice && (
                <>
                  <label className="flex flex-col gap-1">
                    Your reason (required)
                    <textarea className="rounded border bg-background px-2 py-1" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={4000} rows={2} />
                  </label>
                  <div role="radiogroup" aria-label="Applies to" className="flex flex-col gap-1">
                    <label><input type="radio" name="scope" checked={scope === "this_phone"} onChange={() => setScope("this_phone")} /> {r.phone} in this case</label>
                    <label><input type="radio" name="scope" checked={scope === "same_format"} onChange={() => setScope("same_format")} /> {r.phone} and the other phones in this case from the same kind of report</label>
                  </div>
                  <div>
                    <Button size="sm" onClick={() => void saveCorrection()} disabled={!reason.trim() || busy || !!emptying}>Save correction</Button>
                  </div>
                  {emptying && (
                    <div role="alertdialog" aria-label="This correction would leave records empty" className="flex flex-col gap-2 rounded border border-status-review bg-status-review-soft p-2">
                      <p>{emptying.words}</p>
                      {emptying.phones.length > 1 && (
                        <ul>{emptying.phones.map((p) => <li key={p.extraction_id}>{p.phone}: {fmt(p.records)}</li>)}</ul>
                      )}
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
          {error && <p role="alert" className="text-sm">{error}</p>}
        </article>
      </div>
    </section>
  )
}

function Examples({ ex, seen, open, onView, records }: { ex: ReadingExamples; seen: string[]; open: string | null; onView: (k: ExampleKind) => void; records: number }) {
  const viewedN = ex.kinds.filter((k) => seen.includes(k.id)).length
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm">
        Examples drawn from all {fmt(records)} records, one of each kind present.{" "}
        <span role="status">{viewedN} of {ex.kinds.length} kinds viewed</span>
        {ex.apps_not_shown > 0 ? `. ${ex.apps_not_shown} less common apps are not shown as separate kinds.` : ""}
      </p>
      <div className="flex flex-col gap-2">
        {ex.kinds.map((k) => (
          <div key={k.id} className="rounded border bg-card p-2">
            <Button size="sm" variant={open === k.id ? "primary" : "outline"} aria-expanded={open === k.id} onClick={() => onView(k)}>
              Example {k.number}: {k.label}{seen.includes(k.id) ? " (viewed)" : ""}
            </Button>
            {open === k.id && <ExampleView k={k} />}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function PhoneReviewPage() {
  const { id: caseId } = useParams()
  const [params] = useSearchParams()
  const identity = params.get("decision") === "link_phone_identity" ? params.get("identity") : null
  const people = params.get("panel") === "people"
  const [keysOpen, setKeysOpen] = useState(false)
  useEffect(() => {
    installKeymap()
    document.title = "Needs a decision · Loupe"
  }, [])
  if (!caseId) return null
  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4 text-foreground">
      <PageHeader
        title="Needs a decision"
        description="What the system read from this case's phones that a person has not yet checked."
        actions={<Button size="sm" variant="outline" onClick={() => setKeysOpen(true)}>Keys</Button>}
      />
      <PeopleSuggestionsLink caseId={caseId} open={people} />
      {identity && <IdentityLinkGroup caseId={caseId} identityKey={identity} />}
      {people ? <PeopleSuggestions caseId={caseId} /> : <ReadingsGroup caseId={caseId} />}
      {!people && <ReadingRechecks caseId={caseId} />}
      <KeymapOverlay open={keysOpen} onOpenChange={setKeysOpen} />
    </div>
  )
}

/** The way into People suggestions (07 J-7) and back to the readings. */
function PeopleSuggestionsLink({ caseId, open }: { caseId: string; open: boolean }) {
  const sugg = useQuery({ queryKey: ["phone-identity-suggestions", caseId], queryFn: () => identitiesAPI.suggestions(caseId) })
  const base = `/cases/${encodeURIComponent(caseId)}/phone-review`
  return (
    <nav aria-label="Decisions" className="flex gap-3 text-sm">
      {open ? (
        <Link className="underline" to={base}>Readings to check</Link>
      ) : (
        <Link className="underline" to={`${base}?panel=people`}>
          People suggestions{sugg.data ? ` (${sugg.data.total.toLocaleString("en-US")} waiting)` : ""}
        </Link>
      )}
    </nav>
  )
}
