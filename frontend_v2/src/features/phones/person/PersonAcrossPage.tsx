import { useQuery } from "@tanstack/react-query"
import { lazy, Suspense, useMemo, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import type { FeatureCollection, Point } from "geojson"
import { Button } from "@/components/ui/button"
import { ExportDialog } from "@/features/conversations/ExportDialog"
import { failureText, type StreamFilter } from "../api"
import { phoneMark } from "../lib/phone-palette"
import { NextSteps, PhoneTag } from "./parts"
import { clock, day, fmt, phoneFill, plural, usePhoneIndex } from "./screen-lib"
import { momentHref, personAcrossQuery, type Difference, type NextStep, type OnlyList, type PersonAcross, type PersonRecord } from "./person-api"

const PlacesMap = lazy(() => import("@/features/map/components/PlacesMap").then((m) => ({ default: m.PlacesMap })))

const TABS = [
  { id: "stream", label: "Every contact, in time order" },
  { id: "compare", label: "Compare what each phone holds" },
  { id: "volume", label: "When contact rose and fell" },
  { id: "places", label: "Places" },
] as const
type Tab = (typeof TABS)[number]["id"]

const ONLY_WORDS: Record<OnlyList, string> = {
  missing: "contacts missing from a phone",
  missing_unexplained: "contacts missing from a phone for no clear reason",
  missing_not_recording: "contacts missed while a phone was not recording",
  deleted: "contacts deleted on one phone and kept on another",
  clocks: "contacts whose times disagree between phones",
}
const DIFF_ONLY: Partial<Record<Difference["code"], OnlyList>> = { missing: "missing", deleted: "deleted", clocks: "clocks" }
const PAGE = 200

const list = (v: string | null) => (v ? v.split(",").filter(Boolean) : [])

/** Phones redesign screen 3: one person's contact across every app and phone in scope, in one stream. */
export function PersonAcrossPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const people = list(params.get("people"))
  const phones = list(params.get("phones"))
  const withPeople = list(params.get("with"))
  const only = (params.get("only") as OnlyList | null) || null
  const offset = Number(params.get("offset") ?? 0) || 0
  const tab = (TABS.some((t) => t.id === params.get("tab")) ? params.get("tab") : "stream") as Tab
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) if (v) next.set(k, v); else next.delete(k)
    setParams(next)
  }
  const q = useQuery({ ...personAcrossQuery({ caseId, people, phones, withPeople, only, offset, limit: PAGE }), enabled: !!caseId && people.length > 0, retry: false, placeholderData: (prev) => (prev && people.some((k) => prev.person.keys.includes(k)) ? prev : undefined) })
  const indexOf = usePhoneIndex(caseId)
  const [exporting, setExporting] = useState(false)

  if (!people.length)
    return (
      <div className="p-6 text-sm" role="status">
        No person is chosen. Open a person from Conversations, a dossier or the phone list to see their contact across every phone.
      </div>
    )
  if (q.isLoading) return <p role="status" className="p-6 text-sm">Reading their contact on every phone</p>
  if (q.isError || !q.data)
    return (
      <div role="alert" className="p-6 text-sm">
        {failureText(q.error, "Their contact could not be read. Reload the page; if it fails again, choose fewer phones.")}
      </div>
    )
  const d = q.data
  const label = (id: string) => d.phones.find((p) => p.extraction_id === id)?.label ?? "a phone"
  const own = d.phones.filter((p) => p.is_own)
  const others = d.phones.filter((p) => !p.is_own && p.owner_key && !d.person.keys.includes(p.owner_key))
  const scopePhones = d.phones.map((p) => p.extraction_id)
  const filter: StreamFilter = {
    case_id: caseId, phones: scopePhones, kinds: ["message", "call"], expand_person_identities: true,
    ...(withPeople.length ? { participants: [d.person.keys[0], withPeople[0]], participant_mode: "between" as const } : { participants: d.person.keys, participant_mode: "any" as const }),
  }
  const exportWords = d.with ? `${d.person.name} and ${d.with.name} on ${plural(d.phones.length, "phone", "phones")}` : `${d.person.name} on ${plural(d.phones.length, "phone", "phones")}`
  const scoped = params.has("phones")

  const act = (s: NextStep): { to?: string; onClick?: () => void } => {
    if (s.filter) return { onClick: () => set({ only: s.filter!, offset: null, tab: "stream" }) }
    if (s.code === "compare" && s.phones) return { onClick: () => set({ phones: s.phones!.join(","), tab: "compare", only: null, offset: null }) }
    if (s.code === "export") return { onClick: () => setExporting(true) }
    if (s.href) return { to: `/cases/${encodeURIComponent(caseId)}/${s.href}` }
    return {}
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b px-4 sm:px-7 pt-5">
        <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
          <Link className="underline-offset-2 hover:underline" to={`/cases/${encodeURIComponent(caseId)}/phones`}>Phones</Link> / People
        </nav>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{d.person.name}</h1>
            <p className="mt-1 text-[13px] text-muted-foreground">
              {[d.person.identifiers.join(", "), own.length ? `owner of ${own.map((p) => p.label).join(" and ")}` : null].filter(Boolean).join(" · ")}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-[13px]">
              Between {d.person.name} and
              <select className="h-9 rounded-lg border bg-background px-2.5 text-[13px]" value={withPeople[0] ?? ""}
                onChange={(e) => set({ with: e.target.value || null, offset: null, only: null })}>
                <option value="">anyone</option>
                {others.map((p) => (
                  <option key={p.extraction_id} value={p.owner_key!}>{p.owner ?? `the owner of ${p.label}`}</option>
                ))}
                {withPeople[0] && !others.some((p) => p.owner_key === withPeople[0]) && <option value={withPeople[0]}>{d.with?.name ?? withPeople[0]}</option>}
              </select>
            </label>
            <Button variant="outline" size="sm" onClick={() => setExporting(true)} disabled={d.contacts_total === 0} disabledReason="There is no contact to export.">
              Export as PDF
            </Button>
          </div>
        </div>
        <ul aria-label="Phones in scope" className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-2.5">
          {d.phones.map((p) => (
            <li key={p.extraction_id} className="rounded-xl border bg-card px-3.5 py-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[13px] font-semibold">
                  <PhoneTag index={indexOf(p.extraction_id)} label={p.label} />
                  {p.owner && <span className="font-normal text-muted-foreground">{p.owner}</span>}
                </div>
                {d.phones.length > 1 && (
                  <button type="button" className="text-xs text-muted-foreground underline-offset-2 hover:underline"
                    onClick={() => set({ phones: scopePhones.filter((x) => x !== p.extraction_id).join(","), offset: null })}>
                    Leave out
                  </button>
                )}
              </div>
              <div className="mt-2 text-[13px]">
                {p.is_own ? "Their own phone" : p.saved_as.length ? `Saved as ${p.saved_as.map((n) => `“${n}”`).join(", ")}` : "No contact card for them on this phone"}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                <a className="underline-offset-2 hover:underline" href={p.conversations_href}>{plural(p.messages, "message", "messages")} and {plural(p.calls, "call", "calls")}</a>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{p.first ? `${day(p.first)} to ${day(p.last)}` : "No dated contact"}</div>
            </li>
          ))}
        </ul>
        {scoped && (
          <p className="mt-2 text-xs text-muted-foreground">
            Showing {d.phones.length} of the case's phones. <button type="button" className="underline underline-offset-2" onClick={() => set({ phones: null, offset: null })}>Show every phone</button>
          </p>
        )}
        {q.isPlaceholderData && <p role="status" className="mt-2 text-xs text-muted-foreground">Updating the list</p>}
        <div role="tablist" aria-label="Views of their contact" className="mt-3.5 flex flex-wrap gap-5">
          {TABS.map((t) => (
            <button key={t.id} role="tab" type="button" aria-selected={tab === t.id}
              className={`border-b-2 px-0.5 py-2.5 text-[13px] font-medium ${tab === t.id ? "border-foreground text-foreground" : "border-transparent text-muted-foreground"}`}
              onClick={() => set({ tab: t.id === "stream" ? null : t.id })}>
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-wrap">
        <section className="min-w-0 flex-[999_1_560px]" role="tabpanel" aria-label={TABS.find((t) => t.id === tab)!.label}>
          {tab === "stream" && <Stream d={d} only={only} indexOf={indexOf} label={label}
            onPage={(o) => set({ offset: o ? String(o) : null })} onAll={() => set({ only: null, offset: null })} caseId={caseId} />}
          {tab === "compare" && <CompareHoldings d={d} indexOf={indexOf} label={label} />}
          {tab === "volume" && <Volume d={d} indexOf={indexOf} />}
          {tab === "places" && <Places d={d} indexOf={indexOf} label={label} />}
        </section>
        <aside aria-label="What differs between the phones" className="flex max-w-[420px] flex-[1_1_340px] flex-col gap-3.5 border-l bg-muted/30 p-4">
          <h2 className="text-sm font-semibold">What differs between the phones</h2>
          {d.differs.map((x) => {
            const code = DIFF_ONLY[x.code]
            const body = (
              <>
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-semibold">{x.title}</span>
                  <span className="text-sm">{fmt(x.n)}</span>
                </div>
                <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{x.body}</div>
              </>
            )
            if (x.code === "names" && x.n > 0)
              return <Link key={x.code} to={`/cases/${encodeURIComponent(caseId)}/phone-review`} className="block rounded-lg border bg-card p-3 hover:bg-accent">{body}</Link>
            return code && x.n > 0 ? (
              <button key={x.code} type="button" aria-pressed={only === code} className={`block rounded-lg border bg-card p-3 text-left hover:bg-accent ${only === code ? "ring-2 ring-ring" : ""}`}
                onClick={() => set({ only: only === code ? null : code, offset: null, tab: null })}>
                {body}
              </button>
            ) : (
              <div key={x.code} className="rounded-lg border bg-card p-3">{body}</div>
            )
          })}
          <p className="text-xs leading-normal text-muted-foreground">Each card opens those records in the list. A difference is a lead to look into, not a finding.</p>
        </aside>
      </div>

      <div className="border-t px-4 sm:px-7 py-5">
        <NextSteps steps={d.next_steps} intro="Most useful first, from what differs between the phones." act={act} />
      </div>
      {exporting && <ExportDialog caseId={caseId} filter={filter} words={exportWords} open={exporting} onOpenChange={setExporting} />}
    </div>
  )
}

function onWords(r: PersonRecord, label: (id: string) => string) {
  const kept = r.on.filter((e) => !r.deleted_on.includes(e))
  const parts = [`on ${r.on.map(label).join(" and ")}`]
  if (r.missing.length)
    parts.push(`missing from ${r.missing.map((m) => `${label(m.extraction_id)}${m.not_recording ? " (not recording then)" : ""}`).join(" and ")}`)
  if (r.deleted_on.length) parts.push(kept.length ? `deleted from ${r.deleted_on.map(label).join(" and ")}` : "deleted")
  if (r.diff.includes("clocks")) parts.push(`times differ by ${Math.round(r.spread_s)} s`)
  return parts.join(", ")
}

function Stream({ d, only, indexOf, label, onPage, onAll, caseId }: {
  d: PersonAcross; only: OnlyList | null; indexOf: (id: string) => number; label: (id: string) => string
  onPage: (offset: number) => void; onAll: () => void; caseId: string
}) {
  const s = d.summary
  const dayOf = (r: PersonRecord) => (r.row.time.instant ? new Date(r.row.time.instant).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }) : "No time recorded")
  const shownTo = d.offset + d.records.length
  return (
    <div>
      <div className="flex flex-wrap justify-between gap-1.5 border-b px-4 sm:px-6 py-3 text-[13px] text-muted-foreground">
        <span>
          <span className="font-semibold text-foreground">{plural(s.messages, "message", "messages")} and {plural(s.calls, "call", "calls")}</span>{" "}
          across {plural(s.apps.length, "app", "apps")} on {plural(s.phones_holding, "phone", "phones")}
          {s.first ? `, ${day(s.first)} to ${day(s.last)}` : ""}
          {s.no_time > 0 ? `. ${plural(s.no_time, "has", "have")} no time and ${s.no_time === 1 ? "is" : "are"} listed last` : ""}
        </span>
        <span>Messages that appear on more than one phone are shown once, marked with each phone</span>
      </div>
      {only && (
        <div className="flex flex-wrap items-center gap-2 border-b px-4 sm:px-6 py-2 text-[13px]" role="status">
          Showing the {fmt(d.records_total)} {ONLY_WORDS[only]}.
          <button type="button" className="underline underline-offset-2" onClick={onAll}>Show every contact</button>
        </div>
      )}
      {d.records.length === 0 && (
        <p className="px-4 sm:px-6 py-4 text-sm">{only ? "None of their contacts are in this list." : "No message or call with this person is on the phones in scope. Add phones to the scope, or check the person's numbers in Phone review."}</p>
      )}
      <ol aria-label="Their contacts">
        {d.records.map((r, i) => {
          const at = r.row.time.instant
          const dd = dayOf(r)
          const head = i === 0 || dayOf(d.records[i - 1]) !== dd ? dd : null
          const text = r.row.kind === "call" ? r.row.call?.words ?? "Call" : r.row.body ?? r.row.subject ?? "(no text)"
          return (
            <li key={r.row.event_uid}>
              {head && <div className="px-4 sm:px-6 pb-1.5 pt-3 text-xs font-semibold text-muted-foreground">{head}</div>}
              <Link to={`/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(r.row.record_uid)}`}
                className="flex gap-3 border-b px-4 sm:px-6 py-2.5 hover:bg-accent/50">
                <span className="flex w-[26px] shrink-0 gap-0.5 pt-1" aria-hidden>
                  {r.on.map((e) => <span key={e} {...phoneFill(indexOf(e), "size-2 rounded-full")} />)}
                </span>
                <span className="w-[66px] shrink-0 pt-0.5 text-xs text-muted-foreground">{at ? clock(at) : "no time"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{r.row.line}</span> · {r.row.app ?? (r.row.kind === "call" ? "Phone" : "SMS")} · {onWords(r, label)}
                  </span>
                  <span className="mt-0.5 block break-words text-sm">{text}</span>
                </span>
              </Link>
            </li>
          )
        })}
      </ol>
      {d.records_total > d.records.length && (
        <div className="flex flex-wrap items-center gap-2 px-4 sm:px-6 py-3 text-[13px]">
          Showing {fmt(d.offset + 1)} to {fmt(shownTo)} of {fmt(d.records_total)}.
          {d.offset > 0 && <Button size="sm" variant="outline" onClick={() => onPage(Math.max(0, d.offset - d.limit))}>Earlier {fmt(d.limit)}</Button>}
          {shownTo < d.records_total && <Button size="sm" variant="outline" onClick={() => onPage(shownTo)}>Next {fmt(Math.min(d.limit, d.records_total - shownTo))}</Button>}
        </div>
      )}
      <p className="px-4 sm:px-6 py-3 text-xs text-muted-foreground">{d.rule_words}</p>
    </div>
  )
}

function CompareHoldings({ d, indexOf, label }: { d: PersonAcross; indexOf: (id: string) => number; label: (id: string) => string }) {
  const missing = d.differs.find((x) => x.code === "missing")
  return (
    <div className="flex flex-col gap-3 px-4 sm:px-6 py-4 text-sm">
      <p className="text-[13px] text-muted-foreground">Each of their contacts counted once, by the phones that hold it. {d.phones.length > 2 ? `All ${d.phones.length} phones are compared at once.` : ""}</p>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th scope="col" className="p-1.5">Held by</th>
            <th scope="col" className="p-1.5 text-right">Messages</th>
            <th scope="col" className="p-1.5 text-right">Calls</th>
          </tr>
        </thead>
        <tbody>
          {d.compare.map((c) => (
            <tr key={c.on.join(",")} className="border-t">
              <th scope="row" className="p-1.5 text-left font-normal">
                <span className="flex flex-wrap gap-x-2">
                  {c.on.map((e) => <PhoneTag key={e} index={indexOf(e)} label={label(e)} />)}
                  {c.on.length === 1 && <span className="text-muted-foreground">only</span>}
                  {c.on.length > 1 && c.on.length === d.phones.length && <span className="text-muted-foreground">every phone</span>}
                </span>
              </th>
              <td className="p-1.5 text-right tabular-nums">{fmt(c.messages)}</td>
              <td className="p-1.5 text-right tabular-nums">{fmt(c.calls)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {missing && <p className="text-[13px]">{missing.body}</p>}
      {d.summary.no_time > 0 && <p className="text-xs text-muted-foreground">{plural(d.summary.no_time, "contact has", "contacts have")} no time and {d.summary.no_time === 1 ? "is" : "are"} not compared.</p>}
    </div>
  )
}

function Volume({ d, indexOf }: { d: PersonAcross; indexOf: (id: string) => number }) {
  const rows = d.volume.rows
  const max = Math.max(1, ...rows.map((r) => Object.values(r.by_phone).reduce((a, b) => a + b, 0)))
  const ids = d.phones.map((p) => p.extraction_id)
  const name = (b: string) => (d.volume.bucket === "month"
    ? new Date(`${b}-01T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })
    : `Week of ${day(`${b}T00:00:00Z`)}`)
  if (!rows.length) return <p className="px-4 sm:px-6 py-4 text-sm">No dated contact to draw.</p>
  return (
    <div className="flex flex-col gap-3 px-4 sm:px-6 py-4">
      <p className="text-[13px] text-muted-foreground">Messages and calls per {d.volume.bucket}, by the phone that holds them (a contact on two phones counts on each).</p>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th scope="col" className="w-32 p-1.5">{d.volume.bucket === "month" ? "Month" : "Week"}</th>
            <th scope="col" className="p-1.5">Contact</th>
            {d.phones.map((p) => <th key={p.extraction_id} scope="col" className="p-1.5 text-right"><PhoneTag index={indexOf(p.extraction_id)} label={p.label} /></th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.start} className="border-t">
              <th scope="row" className="p-1.5 text-left font-normal">{name(r.start)}</th>
              <td className="p-1.5">
                <span className="flex h-3 w-full" aria-hidden>
                  {ids.map((e) => (r.by_phone[e] ? <span key={e} {...phoneFill(indexOf(e), "h-3", { width: `${(r.by_phone[e] / max) * 100}%` })} /> : null))}
                </span>
              </td>
              {ids.map((e) => <td key={e} className="p-1.5 text-right tabular-nums">{fmt(r.by_phone[e] ?? 0)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Places({ d, indexOf, label }: { d: PersonAcross; indexOf: (id: string) => number; label: (id: string) => string }) {
  const dots = useMemo<FeatureCollection<Point>>(() => ({
    type: "FeatureCollection",
    features: d.places.squares.map((s) => ({ type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] }, properties: { colour: phoneMark(indexOf(s.extraction_id)).light, accuracy: "recorded" } })),
  }), [d.places.squares, indexOf])
  return (
    <div className="flex flex-col gap-3 px-4 sm:px-6 py-4 text-sm">
      <p className="text-[13px]">{d.places.words}</p>
      {d.places.squares.length > 0 && (
        <>
          <Suspense fallback={<p role="status" className="text-sm">Loading the map</p>}>
            <PlacesMap layers={{ dots }} height={320} />
          </Suspense>
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th scope="col" className="p-1.5">Phone</th>
                <th scope="col" className="p-1.5">Where</th>
                <th scope="col" className="p-1.5 text-right">Points</th>
                <th scope="col" className="p-1.5">First and last</th>
              </tr>
            </thead>
            <tbody>
              {d.places.squares.map((s) => (
                <tr key={`${s.extraction_id}:${s.lat}:${s.lon}`} className="border-t">
                  <td className="p-1.5"><PhoneTag index={indexOf(s.extraction_id)} label={label(s.extraction_id)} /></td>
                  <td className="p-1.5 tabular-nums">{s.lat.toFixed(4)}, {s.lon.toFixed(4)}</td>
                  <td className="p-1.5 text-right tabular-nums">{fmt(s.observations)}</td>
                  <td className="p-1.5">{day(s.first)} to {day(s.last)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {d.person.own_phones.length > 0 && d.summary.first && (
        <p className="text-[13px]">
          <Link className="underline underline-offset-2" to={momentHref(d.case_id, d.summary.first, new Date(Math.min(Date.parse(d.summary.first) + 7 * 864e5, Date.parse(d.summary.last ?? d.summary.first) + 1)).toISOString(), d.phones.map((p) => p.extraction_id))}>
            Open their first week of contact on every phone
          </Link>
        </p>
      )}
    </div>
  )
}
