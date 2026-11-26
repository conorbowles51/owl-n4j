import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { phonesQuery } from "../phones-query"
import { PhoneShape } from "../ui/PhoneChip"
import { phoneMark } from "../lib/phone-palette"
import { useUrlScope } from "../ui/use-phone-scope"
import { mentionsAPI, refPath, type Mention, type MentionDetail, type MentionKind, type MentionList, type NextStep } from "./api"
import { Elsewhere } from "./Elsewhere"
import { forgetMentionMarks } from "./marks-store"
import { outcomeHeadline, outcomeTone, verdictText } from "./tones"

/**
 * Screen 8, "What people said, checked against the case": the checkable mentions Loupe read in the phones' texts,
 * counted by kind and outcome, each in its message with the words marked, the selected one's checks per source, the
 * next steps (contradictions first) and how each kind is checked. Every reading is Loupe's until a person confirms or
 * corrects it; every outcome is computed by rules.
 */

const KIND_ORDER: MentionKind[] = ["travel", "meeting", "at_place", "home_away", "plan", "money", "sent", "deleted"]

function fmtWhen(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })
}

function csvCell(v: unknown) {
  const s = String(v ?? "")
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function exportList(list: Mention[]) {
  const head = ["When", "Phone", "From", "To", "Kind", "Words", "Message", "Outcome", "Why", "Reading"]
  const rows = list.map((m) => [m.at, m.phone_label, m.from, m.to.join("; "), m.kind_label, m.phrase, m.body, m.outcome_label, m.why, m.read_by ?? (m.decided_by ? `${m.state} by ${m.decided_by}` : m.state)])
  const blob = new Blob([[head, ...rows].map((r) => r.map(csvCell).join(",")).join("\n")], { type: "text/csv" })
  const a = document.createElement("a")
  a.href = URL.createObjectURL(blob)
  a.download = "mentions-checked.csv"
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function Marked({ m }: { m: Mention }) {
  const body = m.body || m.phrase
  const ok = body.slice(m.start, m.end) === m.phrase
  if (!ok) return <span>{body}</span>
  return (
    <span>
      {body.slice(0, m.start)}
      <mark className="bg-transparent text-foreground underline decoration-status-info decoration-2 underline-offset-4">{m.phrase}</mark>
      {body.slice(m.end)}
    </span>
  )
}

function Pill({ outcome, label }: { outcome: Mention["outcome"]; label: string }) {
  return <span className={cn("inline-flex shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-semibold", outcomeTone(outcome))}>{label}</span>
}

export default function MentionsPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { scope } = useUrlScope(caseId, { restore: true })
  const phones = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  const order = useMemo(() => (phones.data?.phones ?? []).map((p) => p.extraction_id), [phones.data])
  const chosen = scope.phones.map((p) => p.id)
  const kind = (params.get("kind") as MentionKind | null) || null
  const only = params.get("only")
  const selected = params.get("mention")
  const list = useQuery({
    queryKey: ["phone-mentions", caseId, chosen.join(","), kind, only],
    queryFn: () => mentionsAPI.list(caseId, { phones: chosen, kind, outcome: only === "against" ? "against" : only, limit: 200 }),
    enabled: !!caseId,
    refetchInterval: (q) => ((q.state.data as MentionList | undefined)?.phones.some((p) => p.rules?.status === "running" || p.model?.status === "running") ? 4000 : false),
  })
  const pick = selected ?? list.data?.mentions[0]?.id ?? null
  const detail = useQuery({ queryKey: ["phone-mention", caseId, pick], queryFn: () => mentionsAPI.detail(caseId, pick!), enabled: !!caseId && !!pick })
  const set = (k: string, v: string | null) =>
    setParams((p) => {
      const n = new URLSearchParams(p)
      if (v) n.set(k, v)
      else n.delete(k)
      return n
    })
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["phone-mentions", caseId] })
    void qc.invalidateQueries({ queryKey: ["phone-mention", caseId] })
    forgetMentionMarks(caseId)
  }
  const start = useMutation({ mutationFn: (v: { phone: string; reader: "rules" | "model" }) => mentionsAPI.start(caseId, v.phone, v.reader), onSuccess: refresh })
  const colourOf = (phone: string) => Math.max(0, order.indexOf(phone))
  const data = list.data

  const step = (s: NextStep) => {
    if (s.action === "open_mention" && s.mention_id) set("mention", s.mention_id)
    else if (s.action === "filter") {
      setParams((p) => {
        const n = new URLSearchParams(p)
        if (s.kind) n.set("kind", s.kind)
        else n.delete("kind")
        if (s.outcome) n.set("only", s.outcome)
        n.delete("mention")
        return n
      })
    } else if (s.action === "open_map") navigate(`/cases/${encodeURIComponent(caseId)}/map`)
  }

  return (
    <div className="flex min-h-full flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b px-4 pb-4 pt-5 md:px-7">
        <div className="min-w-0">
          <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
            <Link to={`/cases/${encodeURIComponent(caseId)}/phones`} className="underline-offset-2 hover:underline">Phones</Link> / Mentions
          </nav>
          <h1 className="mt-1 text-2xl font-bold">What people said, checked against the case</h1>
          <p className="mt-1 max-w-3xl text-[13px] text-muted-foreground">
            Loupe picks out anything checkable in the messages: trips, meetings, places, plans, being home or away, money, things sent or handed over. Each one is tested against whatever in the case could back it up or contradict it.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" aria-pressed={only === "against"} onClick={() => set("only", only === "against" ? null : "against")}>
            {only === "against" ? "Show every outcome" : "Only contradictions"}
          </Button>
          <Button variant="outline" disabled={!data?.mentions.length} disabledReason="Nothing to export yet" onClick={() => data && exportList(data.mentions)}>
            Export as a list
          </Button>
        </div>
      </header>

      {data && <Readings data={data} colourOf={colourOf} onStart={(phone, reader) => start.mutate({ phone, reader })} busy={start.isPending} error={start.error} />}

      {list.isError && <p role="alert" className="px-7 py-4 text-sm">The mentions could not be read. Reload the page; if it happens again, the reading of this case may need to run again.</p>}
      {list.isLoading && <p className="px-7 py-4 text-sm text-muted-foreground">Reading the mentions…</p>}

      {data && (
        <div className="flex min-h-0 flex-1 flex-wrap">
          <aside aria-label="Mentions by kind" className="flex w-full flex-col gap-3 border-b px-4 py-4 md:w-[280px] md:flex-none md:border-b-0 md:border-r">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Found on {data.phones.length} phone{data.phones.length === 1 ? "" : "s"}
            </div>
            <table className="w-full border-collapse text-[13px]">
              <caption className="sr-only">Mentions by kind and outcome</caption>
              <thead>
                <tr className="text-right text-xs text-muted-foreground">
                  <th scope="col" className="py-1 text-left font-semibold">Kind</th>
                  <th scope="col" className="font-semibold text-status-success">Fits</th>
                  <th scope="col" className="font-semibold text-status-error">Against</th>
                  <th scope="col" className="font-semibold"><abbr title="Can't tell">?</abbr></th>
                </tr>
              </thead>
              <tbody>
                {KIND_ORDER.map((k) => {
                  const c = data.counts.find((x) => x.kind === k)
                  if (!c) return null
                  const on = kind === k
                  const cell = (n: number, o: string, label: string) => (
                    <td className="text-right font-mono">
                      {n ? (
                        <button type="button" className="rounded px-1 underline-offset-2 hover:underline" aria-label={`${n} ${c.label} mentions that ${label}`}
                          onClick={() => setParams((p) => { const x = new URLSearchParams(p); x.set("kind", k); x.set("only", o); x.delete("mention"); return x })}>
                          {n}
                        </button>
                      ) : <span className="text-muted-foreground">0</span>}
                    </td>
                  )
                  return (
                    <tr key={k} className={cn("border-t", on && "bg-accent")}>
                      <th scope="row" className="py-2 text-left font-normal">
                        <button type="button" className="text-left underline-offset-2 hover:underline" aria-pressed={on} onClick={() => setParams((p) => { const x = new URLSearchParams(p); if (on) x.delete("kind"); else x.set("kind", k); x.delete("only"); x.delete("mention"); return x })}>
                          {c.label}
                        </button>
                      </th>
                      {cell(c.fits, "fits", "fit the records")}
                      {cell(c.against, "against", "the records go against")}
                      {cell(c.unknown, "unknown", "nothing tests yet")}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="text-xs leading-relaxed text-muted-foreground">“?” means nothing in the case can test it yet; each one says what would.</p>
            {(kind || only) && (
              <Button variant="ghost" size="sm" className="self-start" onClick={() => setParams((p) => { const x = new URLSearchParams(p); x.delete("kind"); x.delete("only"); return x })}>
                Show every kind and outcome
              </Button>
            )}
          </aside>

          <section aria-label="Mentions in their messages" className="min-w-0 flex-[999_1_420px]">
            <div className="border-b px-5 py-3 text-[13px] text-muted-foreground">
              {kind ? data.counts.find((c) => c.kind === kind)?.label : "Every kind"} · {data.total} mention{data.total === 1 ? "" : "s"}
              {data.shown < data.total ? `, the first ${data.shown} shown` : ""}, contradictions first
            </div>
            {!data.mentions.length && <EmptyList data={data} filtered={!!(kind || only)} />}
            <ul>
              {data.mentions.map((m) => {
                const on = m.id === pick
                const mk = phoneMark(colourOf(m.phone))
                return (
                  <li key={m.id}>
                    <button type="button" onClick={() => set("mention", m.id)} aria-current={on ? "true" : undefined}
                      className={cn("block w-full border-b border-l-[3px] px-5 py-3.5 text-left hover:bg-accent/60", on && "bg-accent")}
                      style={{ borderLeftColor: mk.light }}>
                      <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        {[m, ...m.copies.filter((c) => c.phone !== m.phone)].map((c) => (
                          <span key={c.phone} className="inline-flex items-center gap-1 font-semibold text-foreground"><PhoneShape index={colourOf(c.phone)} />{c.phone_label ?? "A phone"}</span>
                        ))}
                        {m.app && <span>{m.app}</span>}
                        <span className="font-medium text-foreground">{m.from ?? "Unknown sender"}{m.to.length ? ` → ${m.to.join(", ")}` : ""}</span>
                        <span className="font-mono">{fmtWhen(m.at)}</span>
                        <span>{m.kind_label}</span>
                      </span>
                      <span className="mt-1 block text-sm leading-relaxed"><Marked m={m} /></span>
                      <span className="mt-2 flex items-center gap-2">
                        <Pill outcome={m.outcome} label={m.outcome_label} />
                        <span className="text-xs text-muted-foreground">{m.why}</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>

          <aside aria-label="Checks for the selected mention" className="flex w-full flex-col gap-3.5 border-t bg-panel p-5 lg:max-w-[520px] lg:flex-[1_1_420px] lg:border-l lg:border-t-0">
            {pick && detail.data ? <Selected caseId={caseId} d={detail.data} onChanged={refresh} /> : pick && detail.isLoading ? (
              <p className="text-sm text-muted-foreground">Checking the mention against the case…</p>
            ) : detail.isError ? (
              <p role="alert" className="text-sm">This mention could not be checked. It may have been read again; choose it from the list.</p>
            ) : (
              <p className="text-sm text-muted-foreground">Choose a mention to see how it was checked.</p>
            )}
          </aside>
        </div>
      )}

      {data && data.next_steps.length > 0 && (
        <section aria-label="Next steps" className="border-t px-4 py-5 md:px-7">
          <div className="rounded-xl border bg-card p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-base font-bold">Next steps</h2>
              <p className="text-xs text-muted-foreground">Most useful first. Contradictions come before anything that merely fits.</p>
            </div>
            <ol className="mt-2">
              {data.next_steps.map((s) => (
                <li key={s.n} className="flex flex-wrap items-center gap-3.5 border-t py-3">
                  <span className="flex size-6 flex-none items-center justify-center rounded-full bg-muted font-mono text-xs">{s.n}</span>
                  <div className="min-w-0 flex-[1_1_420px]">
                    <div className="text-sm font-semibold">{s.title}</div>
                    <div className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{s.why}</div>
                  </div>
                  <Button variant={s.primary ? "primary" : "outline"} onClick={() => step(s)}>{s.label}</Button>
                </li>
              ))}
            </ol>
          </div>
        </section>
      )}

      {data && (
        <section aria-label="How each kind of mention is checked" className="border-t bg-muted/40 px-4 py-4 md:px-7">
          <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">How each kind of mention is checked</h2>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-x-6 gap-y-2.5">
            {data.how.map((h) => (
              <p key={h.kind} className="text-xs leading-relaxed"><span className="font-semibold">{h.label}</span> <span className="text-muted-foreground">{h.how}</span></p>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function Readings({ data, colourOf, onStart, busy, error }: { data: MentionList; colourOf: (p: string) => number; onStart: (phone: string, reader: "rules" | "model") => void; busy: boolean; error: unknown }) {
  return (
    <section aria-label="How the phones were read" className="flex flex-wrap gap-x-6 gap-y-2 border-b px-4 py-3 text-xs md:px-7">
      {data.phones.map((p) => {
        const r = p.rules
        const m = p.model
        return (
          <div key={p.phone} className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 font-semibold"><PhoneShape index={colourOf(p.phone)} />{p.phone_label ?? "A phone"}</span>
            {!r ? (
              <>
                <span className="text-muted-foreground">{p.texts} texts, not read for mentions yet.</span>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => onStart(p.phone, "rules")}>Read this phone</Button>
              </>
            ) : r.status === "running" ? (
              <span className="text-muted-foreground">Reading: {r.texts_read} of {r.texts_total} texts, {r.mentions_found} mentions so far.</span>
            ) : r.status === "done" ? (
              <>
                <span className="text-muted-foreground">Read by word rules: {r.texts_read} texts, {r.mentions_found} mentions.</span>
                <Button size="sm" variant="ghost" disabled={busy} title="Reads the texts again and checks every mention afresh against the case as it is now. Corrections stay."
                  onClick={() => onStart(p.phone, "rules")}>Read again</Button>
              </>
            ) : (
              <>
                <span className="text-muted-foreground">The reading stopped at {r.texts_read} of {r.texts_total} texts{r.error ? ` (${r.error})` : ""}.</span>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => onStart(p.phone, "rules")}>Carry on</Button>
              </>
            )}
            {p.outside_allowed ? (
              m?.status === "running" ? <span className="text-muted-foreground">Model reading: {m.texts_read} of {m.texts_total}.</span>
                : m?.status === "done" ? <span className="text-muted-foreground">Model read it too: {m.mentions_found} mentions, ${m.cost_usd.toFixed(2)}.</span>
                : <Button size="sm" variant="outline" disabled={busy} onClick={() => onStart(p.phone, "model")}>Read with the model too</Button>
            ) : (
              <span className="text-muted-foreground">Word rules only: this phone's Outside services are not allowed, so its texts do not go to a model.</span>
            )}
          </div>
        )
      })}
      {error ? <p role="alert" className="w-full">{error instanceof Error ? error.message : "The reading could not start."}</p> : null}
    </section>
  )
}

function EmptyList({ data, filtered }: { data: MentionList; filtered: boolean }) {
  const unread = data.phones.filter((p) => !p.rules)
  return (
    <p className="px-5 py-6 text-sm text-muted-foreground">
      {filtered
        ? "No mention of this kind and outcome on the phones chosen. Show every kind and outcome to see the rest."
        : unread.length
          ? `${unread.length} phone${unread.length === 1 ? " has" : "s have"} not been read for mentions yet. Read them above; the mentions appear here as each page is read.`
          : "The phones chosen hold no checkable mentions that Loupe could read."}
    </p>
  )
}

const KIND_LABELS: Record<MentionKind, string> = {
  travel: "Travel", meeting: "Meeting someone", at_place: "Being at a place", home_away: "Home, asleep, away",
  plan: "Plans and times", money: "Money", sent: "Sent or handed over", deleted: "Deleted",
}

function Selected({ caseId, d, onChanged }: { caseId: string; d: MentionDetail; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [kind, setKind] = useState<MentionKind>(d.kind)
  const [place, setPlace] = useState(d.where?.name ?? "")
  const decide = useMutation({
    mutationFn: (body: Parameters<typeof mentionsAPI.decide>[2]) => mentionsAPI.decide(caseId, d.id, body),
    onSuccess: () => { setEditing(false); onChanged() },
  })
  const recheck = useMutation({ mutationFn: () => mentionsAPI.recheck(caseId, d.id), onSuccess: onChanged })
  const chips = [
    `${d.kind_label}${d.where?.name ? `: ${d.where.name}` : ""}`,
    d.window?.label ? `When: ${d.window.label}` : null,
    d.how ? `How: ${d.how}` : null,
    d.who.length ? `About: ${d.who.join(", ")}` : null,
    d.with.length ? `With: ${d.with.join(", ")}` : null,
  ].filter(Boolean) as string[]
  return (
    <>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Selected mention</div>
      <p className="text-base leading-relaxed">“<Marked m={d} />”</p>
      <p className="text-xs text-muted-foreground">
        {d.from ?? "Unknown sender"}{d.to.length ? ` → ${d.to.join(", ")}` : ""} · {d.phone_label ?? "A phone"}{d.app ? ` · ${d.app}` : ""} · {fmtWhen(d.at)} ·{" "}
        <Link className="underline underline-offset-2" to={refPath(caseId, `phone_record:${d.record_uid}`) ?? "#"}>Open the message</Link>
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        {chips.map((c) => <span key={c} className="rounded-full border bg-card px-2.5 py-1 text-xs">{c}</span>)}
        <span className="text-xs text-status-model">
          {d.read_by ?? (d.state === "rejected" ? `Not a mention, said ${d.decided_by}` : `${d.state === "confirmed" ? "Confirmed" : "Corrected"} by ${d.decided_by}`)}
          {d.corrected_fields.length ? ` (changed: ${d.corrected_fields.join(", ")}; Loupe's reading is kept)` : ""}
        </span>
      </div>
      {d.window?.label && d.when?.assumed && <p className="text-xs text-muted-foreground">{d.when.assumed}.</p>}
      <div className="flex flex-wrap gap-2">
        {d.state === "read" && <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => decide.mutate({ action: "confirm" })}>Confirm the reading</Button>}
        <Button size="sm" variant="outline" aria-expanded={editing} onClick={() => setEditing((v) => !v)}>{editing ? "Close" : "Correct it"}</Button>
        {d.state !== "rejected" && <Button size="sm" variant="ghost" disabled={decide.isPending} onClick={() => decide.mutate({ action: "reject" })}>Not a mention</Button>}
        {d.state !== "read" && <Button size="sm" variant="ghost" disabled={decide.isPending} onClick={() => decide.mutate({ action: "restore" })}>Back to Loupe's reading</Button>}
      </div>
      {editing && (
        <form className="flex flex-col gap-2 rounded-lg border bg-card p-3 text-xs" aria-label="Correct the reading"
          onSubmit={(e) => {
            e.preventDefault()
            const values: Record<string, unknown> = {}
            if (kind !== d.kind) values.kind = kind
            if (place !== (d.where?.name ?? "")) values.where = place ? { name: place } : null
            if (Object.keys(values).length) decide.mutate({ action: "correct", values })
          }}>
          <label className="flex flex-col gap-1">Kind
            <select className="rounded border bg-background px-2 py-1 text-sm" value={kind} onChange={(e) => setKind(e.target.value as MentionKind)}>
              {KIND_ORDER.map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">Place, as named
            <input className="rounded border bg-background px-2 py-1 text-sm" value={place} onChange={(e) => setPlace(e.target.value)} />
          </label>
          <Button type="submit" size="sm" variant="outline" className="self-start" disabled={decide.isPending}>Save the correction</Button>
        </form>
      )}
      {decide.isError && <p role="alert" className="text-xs">{decide.error instanceof Error ? decide.error.message : "This could not be saved. Nothing changed."}</p>}

      <div className="rounded-xl border bg-card px-4 py-3.5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className={cn("text-xl font-bold", outcomeHeadline(d.outcome))}>{d.outcome_label}</div>
          <div className="text-xs text-muted-foreground">{d.basis}</div>
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed">{d.why}</p>
        {d.would_test.length > 0 && (
          <div className="mt-2 text-xs text-muted-foreground">
            What would test it:
            <ul className="ml-4 list-disc">{d.would_test.map((w) => <li key={w}>{w}</li>)}</ul>
          </div>
        )}
      </div>

      <ul aria-label="Checks per source">
        {d.checks.map((c, i) => (
          <li key={i} className="flex flex-wrap items-start gap-x-2.5 gap-y-1 border-t py-2.5 sm:flex-nowrap">
            <span className="w-[92px] flex-none rounded-full bg-muted py-0.5 text-center text-[11px] font-semibold">{c.source_label}</span>
            <div className="order-last min-w-0 basis-full sm:order-none sm:basis-auto sm:flex-1">
              <p className="text-[13px] leading-snug">{c.text}</p>
              {c.note && <p className="mt-0.5 text-xs text-muted-foreground">{c.note}</p>}
              {c.refs.length > 0 && (
                <p className="mt-1 flex flex-wrap gap-1">
                  {c.refs.map((r) => {
                    const to = refPath(caseId, r.ref)
                    return to ? (
                      <Link key={r.ref} to={to} className="rounded border bg-muted px-1.5 font-mono text-[11px] no-underline hover:underline">{r.label}</Link>
                    ) : <span key={r.ref} className="rounded border px-1.5 font-mono text-[11px]">{r.label}</span>
                  })}
                  {c.refs_total > c.refs.length && <span className="text-[11px] text-muted-foreground">and {c.refs_total - c.refs.length} more</span>}
                </p>
              )}
            </div>
            <span className={cn("ml-auto flex-none text-xs font-semibold sm:ml-0", verdictText(c.verdict))}>{c.verdict_label}</span>
          </li>
        ))}
        {!d.checks.length && <li className="border-t py-2.5 text-[13px] text-muted-foreground">Nothing in the case could be read for this kind of mention yet.</li>}
      </ul>
      <Elsewhere caseId={caseId} d={d} />
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={recheck.isPending} onClick={() => recheck.mutate()}>{recheck.isPending ? "Checking…" : "Check again"}</Button>
        <Link className="inline-flex h-8 items-center rounded-md border px-3.5 text-[13px] no-underline hover:bg-accent"
          to={`/cases/${encodeURIComponent(caseId)}/map`}>See the map</Link>
      </div>
      <p className="text-[11px] text-muted-foreground">{d.checked_at ? `Checked ${fmtWhen(d.checked_at)}, by rules from the case's records.` : "Checked by rules from the case's records."}</p>
    </>
  )
}
