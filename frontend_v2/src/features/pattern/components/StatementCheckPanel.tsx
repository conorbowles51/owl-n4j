import { useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { phoneLinkHref } from "@/features/phones/phone-links"
import { patternAPI, type Claim, type ClaimKind, type Evaluation, type EvaluationItem, type GroupEvents, type Subject } from "../api"
import { errorWords } from "../lanes-lib"
import { CollectBar } from "./CollectBar"
import { DraftPanel } from "./DraftPanel"

/**
 * Statement check (04 section 9; 07 J-9). Claims are typed here or drafted by the model ("Drafted by <model>, not
 * confirmed" until a person confirms). A confirmed claim is checked; the result is in fixed wording with exact
 * counts, items grouped as supports, undercuts, gaps and context, every item reachable (200 shown at a time; a counted
 * group of context events lists its events on request). "This item is wrong" marks
 * an item with a typed reason; the computed outcome never changes by hand. A stale result shows Check again.
 */
const KIND_WORDS: Record<ClaimKind, string> = {
  inactive: "Not using the phone (for example asleep)", active: "Using the phone", at_place: "At a place",
  not_at_place: "Not at a place", with_subject: "With someone", apart_from_subject: "Apart from someone",
  no_contact: "No contact with someone", contact: "In contact with someone",
}
const GROUPS: { role: EvaluationItem["role"]; title: string }[] = [
  { role: "supporting", title: "Supports" }, { role: "contradicting", title: "Undercuts" },
  { role: "gap", title: "Gaps" }, { role: "context", title: "Context" },
]

function utc(t: string) {
  return `${new Date(t).toISOString().replace("T", " ").slice(0, 16)} UTC`
}

function same(a: Subject, b: Subject) {
  return JSON.stringify(a) === JSON.stringify(b)
}

export function StatementCheckPanel({ caseId, subject }: { caseId: string; subject: Subject }) {
  const qc = useQueryClient()
  const claims = useQuery({ queryKey: ["pattern-claims", caseId], queryFn: () => patternAPI.claims(caseId) })
  const mine = (claims.data?.items || []).filter((c) => c.status !== "withdrawn" && same(c.subject, subject))
  const [current, setCurrent] = useState<string | null>(null)
  const claim = mine.find((c) => c.id === current) || mine.filter((c) => c.status === "confirmed").pop() || mine[mine.length - 1]
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setEv(null)
    if (!claim || claim.status !== "confirmed") return
    patternAPI.evaluations(caseId, claim.id).then(async (list) => {
      const last = list.items[list.items.length - 1]
      const out = last ? await patternAPI.evaluation(caseId, claim.id, last.evaluation_id) : await patternAPI.evaluate(caseId, claim.id)
      if (live) setEv(out)
    }).catch((e) => live && setErr(errorWords(e)))
    return () => { live = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the claim's id, status and version, not the object identity
  }, [caseId, claim?.id, claim?.status, claim?.version])

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setErr(null)
    try { await fn(); await qc.invalidateQueries({ queryKey: ["pattern-claims", caseId] }) } catch (e) { setErr(errorWords(e)) } finally { setBusy(null) }
  }

  return (
    <section aria-label="Statement check" className="flex flex-col gap-3 text-sm">
      <ClaimForm caseId={caseId} subject={subject} onMade={(c) => { setCurrent(c.id); void qc.invalidateQueries({ queryKey: ["pattern-claims", caseId] }) }} />
      <DraftPanel caseId={caseId} subject={subject} onAccepted={() => void qc.invalidateQueries({ queryKey: ["pattern-claims", caseId] })} />
      <div>
        <h3 className="font-medium">Statements for this phone or person ({mine.length.toLocaleString()})</h3>
        <ul className="flex flex-col gap-1">
          {mine.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2">
              <button className={`underline-offset-2 hover:underline ${claim?.id === c.id ? "font-medium" : ""}`} onClick={() => setCurrent(c.id)}>
                {KIND_WORDS[c.kind]}{c.window_text ? `: "${c.window_text}"` : ""}
              </button>
              <span className="text-xs text-muted-foreground">{c.status_words}</span>
              {c.status === "draft" && c.missing_for_confirm.length === 0 && (
                <Button size="sm" variant="outline" disabled={!!busy} onClick={() => act("Confirming…", () => patternAPI.confirmClaim(caseId, c.id, c.version))}>Confirm</Button>
              )}
              {c.status === "draft" && c.missing_for_confirm.length > 0 && (
                <span className="text-xs">Settle before confirming: {c.missing_for_confirm.join(", ").replace(/_/g, " ")}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
      {busy && <p aria-live="polite">{busy}</p>}
      {err && <p role="alert" className="text-destructive">{err}</p>}
      {claim && claim.status === "confirmed" && !ev && !err && <p className="text-muted-foreground">Checking the statement…</p>}
      {ev && claim && <EvaluationView caseId={caseId} claim={claim} ev={ev}
        onAgain={() => act("Checking again…", async () => setEv(await patternAPI.evaluate(caseId, claim.id)))}
        onDispute={(o) => {
          const reason = window.prompt("Why is this item wrong?")
          if (reason && reason.trim()) void act("Marking the item…", async () => {
            await patternAPI.dispute(caseId, claim.id, ev.evaluation_id, o, reason.trim())
            setEv(await patternAPI.evaluation(caseId, claim.id, ev.evaluation_id))
          })
        }} />}
    </section>
  )
}

function EvaluationView({ caseId, claim, ev, onAgain, onDispute }: {
  caseId: string; claim: Claim; ev: Evaluation; onAgain: () => void; onDispute: (ordinal: number) => void
}) {
  return (
    <div className="flex flex-col gap-2 rounded border p-3">
      <p className="font-medium">{ev.outcome_words}</p>
      <p className="text-xs text-muted-foreground">Basis: {ev.outcome_basis}. {ev.total_items.toLocaleString()} items, all listed.
        {ev.disputed_items ? ` ${ev.disputed_items.toLocaleString()} marked wrong.` : ""}</p>
      {ev.stale && (
        <p className="flex items-center gap-2">The phones' reading or the statement changed since this check.
          <Button size="sm" onClick={onAgain}>Check again</Button></p>
      )}
      {GROUPS.map((g) => <RoleList key={g.role} caseId={caseId} claimId={claim.id} ev={ev} role={g.role} title={g.title}
        onDispute={onDispute} />)}
      <h4 className="font-medium">What would contradict this?</h4>
      <ul>{(ev.summary.not_yet_checked || []).map((n) => <li key={n.code}>{n.words}</li>)}</ul>
      <p className="text-xs text-muted-foreground">Statement {claim.window_text ? `"${claim.window_text}" ` : ""}checked from {utc(ev.window.start)} to {utc(ev.window.end)}{ev.window.zone !== "UTC" ? ` (the statement's zone: ${ev.window.zone})` : ""}.</p>
      <CollectBar caseId={caseId} noun="statement check" origin="Added from the statement check"
        links={[{ target_type: "statement_check", target_id: ev.evaluation_id, label: `Statement check: ${claim.window_text || claim.kind}`, source_anchor: {} }]} />
    </div>
  )
}

const PAGE = 200

/** One role's items, 200 at a time with the count shown, so a long list never hangs the page and every item stays
 * reachable. A counted group of context events (04 decision 37) opens its own list of events. */
export function RoleList({ caseId, claimId, ev, role, title, onDispute }: {
  caseId: string; claimId: string; ev: Evaluation; role: EvaluationItem["role"]; title: string; onDispute: (ordinal: number) => void
}) {
  const [shown, setShown] = useState(PAGE)
  const items = ev.items.filter((i) => i.role === role)
  const total = items.length
  return (
    <div>
      <h4 className="font-medium">{title} ({total.toLocaleString("en-US")})</h4>
      <ul className="flex flex-col gap-0.5">
        {items.slice(0, shown).map((i) => {
          const href = i.record_uid ? phoneLinkHref(caseId, { target_type: "phone_record", target_id: i.record_uid }) : null
          return (
            <li key={i.ordinal} className="flex flex-col">
              <div className="flex flex-wrap items-center gap-2">
                <span>{i.at_utc ? utc(i.at_utc) : ""}</span>
                <span>{i.explanation}</span>
                {i.strength && <span className="text-xs text-muted-foreground">{i.strength}</span>}
                {href && <a className="text-xs underline" href={href}>Open the record</a>}
                {i.disputed
                  ? <span className="text-xs">Marked wrong by {i.disputed.actor_name}: {i.disputed.reason}</span>
                  : <button className="text-xs underline" onClick={() => onDispute(i.ordinal)}>This item is wrong</button>}
              </div>
              {i.ref_kind === "event_group" && <GroupEventsList caseId={caseId} claimId={claimId} evaluationId={ev.evaluation_id} item={i} />}
            </li>
          )
        })}
      </ul>
      {total > shown && (
        <p className="flex items-center gap-2 text-xs">Showing {shown.toLocaleString("en-US")} of {total.toLocaleString("en-US")}.
          <button className="underline" onClick={() => setShown(shown + PAGE)}>Show {Math.min(PAGE, total - shown).toLocaleString("en-US")} more</button></p>
      )}
    </div>
  )
}

function GroupEventsList({ caseId, claimId, evaluationId, item }: { caseId: string; claimId: string; evaluationId: string; item: EvaluationItem }) {
  const [open, setOpen] = useState(false)
  const [pages, setPages] = useState<GroupEvents[]>([])
  const [err, setErr] = useState<string | null>(null)
  const count = Number((item.display as { count?: number }).count || 0)
  async function more(cursor: number) {
    setErr(null)
    try {
      const page = await patternAPI.groupEvents(caseId, claimId, evaluationId, item.ordinal, cursor)
      setPages((p) => [...p, page])
    } catch (e) { setErr(errorWords(e)) }
  }
  const last = pages[pages.length - 1]
  const rows = pages.flatMap((p) => p.items)
  if (!open) return <button className="self-start text-xs underline" onClick={() => { setOpen(true); if (!pages.length) void more(0) }}>Show the {count.toLocaleString("en-US")} events</button>
  return (
    <div className="ml-4 flex flex-col gap-0.5 text-xs">
      {err && <p role="alert" className="text-destructive">{err}</p>}
      {last?.changed_since_check && <p>The phone's readings changed after this check: {last.total.toLocaleString("en-US")} events now, {last.stored_count.toLocaleString("en-US")} when checked.</p>}
      <ul>
        {rows.map((r) => {
          const href = r.record_uid ? phoneLinkHref(caseId, { target_type: "phone_record", target_id: r.record_uid }) : null
          return <li key={r.activity_event_id} className="flex flex-wrap gap-2"><span>{utc(r.at_utc)}</span><span>{r.display.type}, {r.display.field}</span>
            {r.display.source_app && <span>{r.display.source_app}</span>}{href && <a className="underline" href={href}>Open the record</a>}</li>
        })}
      </ul>
      {last && <p className="flex items-center gap-2">Showing {rows.length.toLocaleString("en-US")} of {last.total.toLocaleString("en-US")}.
        {last.next_cursor !== null && <button className="underline" onClick={() => void more(last.next_cursor as number)}>Show more</button>}
        <button className="underline" onClick={() => setOpen(false)}>Hide</button></p>}
    </div>
  )
}

function ClaimForm({ caseId, subject, onMade }: { caseId: string; subject: Subject; onMade: (c: Claim) => void }) {
  const [kind, setKind] = useState<ClaimKind>("inactive")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [zone, setZone] = useState("UTC")
  const [words, setWords] = useState("")
  const [place, setPlace] = useState({ lat: "", lon: "", radius_m: "100" })
  const [err, setErr] = useState<string | null>(null)
  async function save() {
    setErr(null)
    const toIso = (v: string) => v ? new Date(`${v}:00Z`).toISOString() : undefined
    const fields: Record<string, unknown> = { kind, subject, window_text: words || undefined, window_zone: zone,
      window_start: toIso(start), window_end: toIso(end) }
    if (kind === "at_place" || kind === "not_at_place") fields.place = place.lat && place.lon ? { lat: Number(place.lat), lon: Number(place.lon), radius_m: Number(place.radius_m) } : { text: words }
    try { onMade(await patternAPI.createClaim(caseId, fields)) } catch (e) { setErr(errorWords(e)) }
  }
  return (
    <details className="rounded border p-2">
      <summary className="cursor-pointer font-medium">Enter a statement</summary>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
        <label className="flex flex-col">What the statement says
          <select value={kind} onChange={(e) => setKind(e.target.value as ClaimKind)} className="rounded border bg-background px-2 py-1">
            {Object.entries(KIND_WORDS).map(([k, w]) => <option key={k} value={k}>{w}</option>)}
          </select></label>
        <label className="flex flex-col">The statement's own words<input value={words} onChange={(e) => setWords(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
        <label className="flex flex-col">From (UTC)<input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
        <label className="flex flex-col">Until (UTC)<input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
        <label className="flex flex-col">Zone the statement uses<input value={zone} onChange={(e) => setZone(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
        {(kind === "at_place" || kind === "not_at_place") && (
          <div className="flex gap-1">
            <input aria-label="Latitude" placeholder="Latitude" value={place.lat} onChange={(e) => setPlace({ ...place, lat: e.target.value })} className="w-24 rounded border bg-background px-2 py-1" />
            <input aria-label="Longitude" placeholder="Longitude" value={place.lon} onChange={(e) => setPlace({ ...place, lon: e.target.value })} className="w-24 rounded border bg-background px-2 py-1" />
            <input aria-label="Radius in metres" value={place.radius_m} onChange={(e) => setPlace({ ...place, radius_m: e.target.value })} className="w-20 rounded border bg-background px-2 py-1" />
          </div>
        )}
      </div>
      <Button size="sm" className="mt-2" onClick={save}>Save as not confirmed</Button>
      {err && <p role="alert" className="text-destructive">{err}</p>}
    </details>
  )
}
