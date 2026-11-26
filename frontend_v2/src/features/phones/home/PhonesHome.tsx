import { lazy, Suspense, useMemo, useRef, useState, type FormEvent } from "react"
import { useQueries, useQuery } from "@tanstack/react-query"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { StreamList } from "@/features/phones/components/StreamList"
import { useStream } from "@/features/phones/hooks/use-stream"
import { DEFAULT_VIEW, viewToFilter } from "@/features/phones/lib/filter-url"
import { layersOn, toggleLayer } from "@/features/phones/lib/phone-layers"
import { phoneSettingsQuery } from "@/features/phones/phone-queries"
import { phonesQuery } from "@/features/phones/phones-query"
import type { StreamRow } from "@/features/phones/schemas"
import { PhoneShape } from "@/features/phones/ui/PhoneChip"
import { scopeHref } from "@/features/phones/ui/scope"
import { useCasePhones } from "@/features/phones/ui/use-case-phones"
import { useUrlScope } from "@/features/phones/ui/use-phone-scope"
import { LENS_SOURCE, lensBuckets, lensIndex, type LensFilter } from "@/features/timeline/lens/lens-api"
import { ActivityStrip } from "./ActivityStrip"
import { copyKey, phonesByCopy, spanWords } from "./home-words"
import { HomeRecordPanel } from "./HomeRecordPanel"
import { ALL_GROUP, DEFAULT_WHAT, groupCount, homeFacets, WHAT_GROUPS, whatGroup, type CopiesOn, type FacetPart, type HomeFacets, type StateKey } from "./home-api"

const ExportDialog = lazy(() => import("@/features/conversations/ExportDialog").then((m) => ({ default: m.ExportDialog })))
const n = (x: number) => x.toLocaleString("en-US")
/** Sibling screens of the phones redesign, linked only once their page is in this build (lx-phonesearch's Search,
 * lx-phoneask's Ask), so the page never links to an address that is not there yet. */
const HAS_SEARCH = Object.keys(import.meta.glob("/src/features/phones/search/PhoneSearchPage.tsx")).length > 0
const HAS_ASK = Object.keys(import.meta.glob("/src/features/phones/ask/*Page.tsx")).length > 0

/** The phone screens that used to have their own side-menu entries, reached from here now. */
const MORE: [string, string][] = [
  ["conversations", "Threads and people"], ["phone-patterns", "Patterns of life"], ["phone-money", "Money on the phones"],
  ["phones/mentions", "What people said, checked"], ["phone-analyses", "Analyses"], ["phone-review", "Needs a decision"],
]

function Facet({ label, count, on, onClick, disabledReason }: { label: string; count: number | null | undefined; on: boolean; onClick: () => void; disabledReason?: string }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} disabled={!!disabledReason} title={disabledReason}
      className={cn("flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm text-foreground/85 hover:bg-muted disabled:opacity-60",
        on && "bg-muted font-medium text-foreground ring-1 ring-inset ring-border")}>
      <span className="min-w-0 truncate">{label}</span>
      {/* on the chosen facet's grey the muted colour measured 4.49:1 in the light theme; full colour there */}
      <span className={cn("font-mono text-xs tabular-nums", on ? "text-foreground" : "text-muted-foreground")} data-testid="facet-count">{count === undefined ? "…" : count === null ? "" : n(count)}</span>
    </button>
  )
}

export function PhonesHome({ caseId, caseName }: { caseId: string; caseName: string }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const set = (k: string, v: string | null) => setParams((p) => { const q = new URLSearchParams(p); if (v) q.set(k, v); else q.delete(k); return q }, { replace: true })
  const what = whatGroup(params.get("what") ?? DEFAULT_WHAT)
  const state = (params.get("state") as StateKey | null) ?? null
  const words = params.get("q") ?? ""
  const [typed, setTyped] = useState(words)
  const carried = useUrlScope(caseId, { people: true, window: true })
  const scope = carried.scope
  const phones = useCasePhones(caseId)
  const all = phones.map((p) => p.id)
  const on = layersOn(all, scope.phones.map((p) => p.id))
  const phoneIndex = (id: string) => Math.max(0, phones.findIndex((p) => p.id === id))
  const setPhones = (chosen: string[]) => carried.apply({ ...scope, phones: chosen.map((id) => ({ id, label: phones.find((p) => p.id === id)?.label ?? "A phone", index: phoneIndex(id) })) })
  const summaries = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  const settings = useQuery({ ...phoneSettingsQuery(caseId), enabled: !!caseId })
  const zoneName = settings.data?.effective?.name ?? "UTC"

  const sig = JSON.stringify([scope.people.map((p) => p.key), scope.mode, scope.phones.map((p) => p.id), scope.window])
  const scoped = useMemo<Partial<LensFilter>>(() => {
    const f = viewToFilter(caseId, { ...DEFAULT_VIEW, people: scope.people.map((p) => p.key), mode: scope.mode, phones: scope.phones.map((p) => p.id), from: scope.window?.from ?? null, to: scope.window?.to ?? null }, zoneName)
    return { phones: f.phones, participants: f.participants, participant_mode: f.participant_mode, group_scope: f.group_scope, from_instant: f.from_instant, to_instant: f.to_instant }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the signature is the scope
  }, [sig, caseId, zoneName])
  const filter = useMemo<LensFilter & { copies_on?: CopiesOn }>(() => ({
    case_id: caseId, lens_kinds: what.kinds, lane_by: "phone", ...scoped,
    ...(words.trim() ? { text: { query: words.trim() } } : {}),
    ...(state === "deleted" ? { deleted_states: ["Deleted", "Trash"] } : {}),
    ...(state === "one" || state === "many" ? { copies_on: state } : {}),
  }), [caseId, what.key, scoped, words, state]) // eslint-disable-line react-hooks/exhaustive-deps -- what.key names the kinds
  const ready = !settings.isPending && phones.length > 0
  const stream = useStream(ready ? filter : null, { source: LENS_SOURCE })

  const parts: FacetPart[] = ["kinds", "people", "states", "phones"]
  const facetQs = useQueries({ queries: parts.map((part) => ({ queryKey: ["phone-home-facets", part, filter], queryFn: () => homeFacets(filter, part), enabled: ready, staleTime: 30_000 })) })
  const facets: HomeFacets = Object.assign({ case_id: caseId }, ...facetQs.map((q) => q.data ?? {}))
  const facetFailed = facetQs.some((q) => q.isError)

  // the strip: every filter but the dates, so the weeks picked can be changed
  const undated = useMemo(() => ({ ...filter, from_instant: undefined, to_instant: undefined }), [filter])
  const undatedIdx = useQuery({ queryKey: ["phone-home-undated", undated], queryFn: () => lensIndex(undated), enabled: ready && !!scope.window })
  const stripIdx = scope.window ? undatedIdx.data : stream.index
  const days = stripIdx?.items.map((d) => d.day).sort() ?? []
  const start = days.length ? new Date(Date.parse(`${days[0]}T00:00:00Z`) - 86400000).toISOString() : null
  const end = days.length ? new Date(Date.parse(`${days[days.length - 1]}T00:00:00Z`) + 2 * 86400000).toISOString() : null
  const buckets = useQuery({
    queryKey: ["phone-home-weeks", undated, stripIdx?.snapshot, start, end],
    queryFn: () => lensBuckets(undated, stripIdx!.snapshot, start!, end!, "week"),
    enabled: !!stripIdx && !!start && !!end, retry: 1,
  })

  // copies on other phones among the loaded rows: the row badge and the record panel's fallback check
  const loaded = useMemo(() => {
    const rows: StreamRow[] = []
    if (stream.count <= 20000) for (let i = 0; i < stream.count; i++) { const it = stream.item(i); if (it.type === "row" && it.row) rows.push(it.row) }
    return phonesByCopy(rows)
  }, [stream.rowsVersion, stream.count]) // eslint-disable-line react-hooks/exhaustive-deps -- rowsVersion marks new rows
  const alsoOn = (row: StreamRow) => { const k = copyKey(row); return k ? [...(loaded.get(k) ?? new Map<string, string>())].filter(([id]) => id !== row.phone.extraction_id).map(([, l]) => l) : [] }

  const [focused, setFocused] = useState<StreamRow | null>(null)
  const [exporting, setExporting] = useState(false)
  const searchBox = useRef<HTMLInputElement>(null)
  const total = stream.index?.counts.entries ?? stream.total
  const onWords = `${on.length === all.length ? `${n(on.length)} ${on.length === 1 ? "phone" : "phones"}` : `${n(on.length)} of ${n(all.length)} phones`}`
  const listWords = [what.label, words.trim() ? `with "${words.trim()}"` : null, scope.people.length ? `involving ${scope.people.map((p) => p.label).join(", ")}` : null, state ? facets.states?.find((s) => s.key === state)?.label?.toLowerCase() : null, scope.window ? `${scope.window.from} to ${scope.window.to}` : null].filter(Boolean).join(", ")
  const submit = (e: FormEvent) => {
    e.preventDefault()
    set("q", typed.trim() || null)
  }
  const thatDay = (row: StreamRow) => {
    const day = row.time.instant!.slice(0, 10)
    carried.apply({ ...scope, phones: [], people: [], window: { from: day, to: day } })
    set("what", "all")
  }
  const personOn = (key: string) => scope.people.some((p) => p.key === key)
  const togglePerson = (key: string, label: string) => carried.apply({ ...scope, people: personOn(key) ? scope.people.filter((p) => p.key !== key) : [...scope.people, { key, label }] })
  const askHref = scopeHref(`/cases/${encodeURIComponent(caseId)}/phones/ask`, scope, typed.trim() ? { q: typed.trim() } : {})
  const active = (summaries.data?.phones ?? []).filter((p) => p.standing !== "superseded")
  const span = (id: string) => facets.phones?.find((s) => s.extraction_id === id)

  return (
    // Wide (the facets, the list and the panel side by side): the page fills its box and the list scrolls inside it.
    // Narrow: the page scrolls as a whole and the list keeps a set height, so it never takes its full content height.
    <div className="@container flex min-h-0 flex-1 flex-col">
      <header className="flex flex-col gap-4 border-b px-4 pb-4 pt-5 md:px-7">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs text-muted-foreground">{caseName}</p>
            <h1 className="mt-0.5 text-2xl font-bold tracking-tight">Phones</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm"><Link to={`/cases/${encodeURIComponent(caseId)}/evidence?add=phone`}>Add a phone</Link></Button>
            <Button variant="outline" size="sm" onClick={() => setExporting(true)} disabled={!total} disabledReason="Nothing is shown to export.">Export what is shown</Button>
          </div>
        </div>
        <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(15rem,1fr))]" role="group" aria-label="Phones in this case">
          {active.map((p) => {
            const isOn = on.includes(p.extraction_id)
            const s = span(p.extraction_id)
            return (
              <div key={p.extraction_id} className={cn("flex items-start gap-3 rounded-xl border bg-card px-3.5 py-3", !isOn && "opacity-70")} data-phone-card={p.extraction_id} data-on={isOn}>
                <PhoneShape index={phoneIndex(p.extraction_id)} className="mt-1 size-3" />
                <div className="min-w-0 flex-1">
                  <div className="flex justify-between gap-2">
                    <p className="min-w-0 text-sm font-semibold"><Link className="hover:underline" to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(p.extraction_id)}`}>{p.label}</Link> <span className="font-normal text-muted-foreground">· {p.owner?.name ?? "owner not named"}</span></p>
                    <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                      <input type="checkbox" checked={isOn} onChange={() => setPhones(toggleLayer(all, scope.phones.map((x) => x.id), p.extraction_id))} aria-label={`${p.label} on`} />
                      On
                    </label>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {[p.device.manufacturer, p.device.model].filter(Boolean).join(" ") || "Phone report"} · {s ? spanWords(s.first_day, s.last_day) : facetQs[3].isPending ? "dates being read" : "no dated records"}
                  </p>
                  <p className="mt-1.5 font-mono text-xs text-foreground/85">{n(p.counts.messages)} messages · {n(p.counts.calls)} calls · {n(p.counts.locations)} places</p>
                  <Link className="mt-1 inline-block text-xs underline underline-offset-2" aria-label={`About this phone: ${p.label}`} to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(p.extraction_id)}`}>About this phone</Link>
                </div>
              </div>
            )
          })}
        </div>
        {on.length < all.length && <p role="status" className="text-xs text-muted-foreground">{n(on.length)} of {n(all.length)} phones are on. Every list, count and week below leaves the others out. <button type="button" className="underline" onClick={() => setPhones([])}>Turn every phone on</button></p>}
        <form role="search" onSubmit={submit} className="flex flex-wrap items-center gap-2.5">
          <div role="radiogroup" aria-label="Search or ask" className="flex h-12 rounded-lg border bg-card p-1">
            <button type="button" role="radio" aria-checked="true" className="rounded-md bg-muted px-3.5 text-sm font-semibold">Search words</button>
            <button type="button" role="radio" aria-checked="false" className="rounded-md px-3.5 text-sm text-muted-foreground hover:text-foreground disabled:opacity-60"
              disabled={!HAS_ASK} title={HAS_ASK ? undefined : "Asking questions of the phones is not on this server yet. Search words works now."}
              onClick={() => navigate(askHref)}>Ask a question</button>
          </div>
          <label htmlFor="phones-q" className="sr-only">Search every phone that is on</label>
          <div className="flex h-12 min-w-[14rem] flex-1 items-center gap-2.5 rounded-xl border bg-card px-3.5">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden className="text-muted-foreground"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
            <input id="phones-q" ref={searchBox} type="search" value={typed} onChange={(e) => setTyped(e.target.value)}
              placeholder={`Search ${on.length === 1 ? "1 phone" : `all ${n(on.length)} phones`}: messages, calls, contacts, places, apps, web, files, deleted items`}
              className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
          </div>
          <Button type="submit" className="h-12 px-6">Search</Button>
        </form>
        {words.trim() && <p className="text-xs text-muted-foreground">The list shows every kind of record holding "{words.trim()}" on the phones that are on. {HAS_SEARCH && <><Link className="underline" to={scopeHref(`/cases/${encodeURIComponent(caseId)}/phones/search`, scope, { q: words.trim() })}>See the matches grouped by kind and phone</Link> · </>}<button type="button" className="underline" onClick={() => { setTyped(""); set("q", null) }}>Clear the words</button></p>}
      </header>

      <div className="flex flex-wrap @min-[62rem]:min-h-[24rem] @min-[62rem]:flex-1 @min-[62rem]:flex-nowrap" data-testid="phones-home-body">
        <aside aria-label="Narrow" className="flex w-full flex-col gap-5 border-b px-3.5 py-4 md:w-60 md:flex-none md:border-b-0 md:border-r @min-[62rem]:overflow-y-auto">
          {facetFailed && <p role="alert" className="text-xs">Some counts could not be loaded; the list is complete without them. Reload the page to count again.</p>}
          <div className="flex flex-col gap-0.5" role="group" aria-label="What">
            <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">What</p>
            {[...WHAT_GROUPS, ALL_GROUP].map((g) => (
              <Facet key={g.key} label={g.label} count={facets.kinds ? groupCount(facets.kinds, g.kinds) : undefined} on={what.key === g.key} onClick={() => set("what", g.key === DEFAULT_WHAT ? null : g.key)} />
            ))}
          </div>
          <div className="flex flex-col gap-0.5" role="group" aria-label="Who">
            <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Who</p>
            {facets.people_applies === false && <p className="px-2 text-xs text-muted-foreground">People are counted in messages and calls. Choose Messages and calls to narrow by person.</p>}
            {facets.people?.map((p) => <Facet key={p.key} label={p.label} count={p.count} on={personOn(p.key)} onClick={() => togglePerson(p.key, p.label)} />)}
            {scope.people.filter((p) => !facets.people?.some((x) => x.key === p.key)).map((p) => <Facet key={p.key} label={p.label} count={null} on onClick={() => togglePerson(p.key, p.label)} />)}
            {!!facets.people_total && facets.people_total > (facets.people?.length ?? 0) && (
              <Link className="px-2 py-1 text-xs underline underline-offset-2" to={scopeHref(`/cases/${encodeURIComponent(caseId)}/conversations`, scope, { tab: "people" })}>All people ({n(facets.people_total)})</Link>
            )}
            {facets.people && facets.people.length === 0 && facets.people_applies && <p className="px-2 text-xs text-muted-foreground">No one but the phones' owners takes part in what is shown.</p>}
          </div>
          <div className="flex flex-col gap-0.5" role="group" aria-label="State">
            <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">State</p>
            {(facets.states ?? [{ key: "deleted", label: "Deleted or in trash" }, { key: "one", label: "On one phone only" }, { key: "many", label: "On more than one phone" }] as HomeFacets["states"] & object).map((s) => (
              <Facet key={s.key} label={s.label} count={facets.states ? s.count : undefined} on={state === s.key} onClick={() => set("state", state === s.key ? null : s.key)}
                disabledReason={s.applies === false ? "Copies on other phones are judged for messages and calls only." : s.key !== "deleted" && on.length < 2 ? "Turn on a second phone to compare." : undefined} />
            ))}
            {facets.states_note && <p className="px-2 pt-1 text-[11px] leading-snug text-muted-foreground">{facets.states_note}</p>}
          </div>
          <nav aria-label="More about these phones" className="flex flex-col gap-0.5">
            <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">More about these phones</p>
            {MORE.map(([path, label]) => (
              <Link key={path} className="rounded-md px-2 py-1 text-sm text-foreground/85 underline-offset-2 hover:bg-muted hover:underline" to={scopeHref(`/cases/${encodeURIComponent(caseId)}/${path}`, scope)}>{label}</Link>
            ))}
          </nav>
        </aside>

        <section aria-label="Everything on the phones in time order" className="flex min-w-0 flex-[999_1_26rem] flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="text-sm font-semibold">{what.label}</span>
              <span className="text-sm text-muted-foreground" role="status">
                {stream.status === "ready" ? `${n(total)} on ${onWords}, oldest first` : stream.status === "error" ? "" : "Counting"}
              </span>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {state && <Button size="sm" variant="outline" className="h-7 rounded-full text-xs" onClick={() => set("state", null)}>{facets.states?.find((s) => s.key === state)?.label ?? "State"} ×</Button>}
              {scope.people.map((p) => <Button key={p.key} size="sm" variant="outline" className="h-7 rounded-full text-xs" onClick={() => togglePerson(p.key, p.label)}>{p.label} ×</Button>)}
              {what.key === "comms" && <Button asChild size="sm" variant="outline" className="h-7 text-xs"><Link to={scopeHref(`/cases/${encodeURIComponent(caseId)}/conversations`, scope)}>Group into threads</Link></Button>}
            </div>
          </div>
          {stream.status === "error" && <p role="alert" className="p-5 text-sm">{stream.error} Reload the page to try again.</p>}
          {stream.status === "ready" && total === 0 && (
            <p className="p-5 text-sm text-muted-foreground">Nothing on the phones that are on matches {listWords || "this"}. Turn more phones on, choose another kind of record or clear the filters.</p>
          )}
          {ready && (
            <StreamList
              key={JSON.stringify(filter)}
              stream={stream}
              caseId={caseId}
              caseName={caseName}
              filterWords={listWords}
              zoneName={stream.index?.zone.label ?? "UTC"}
              zone={stream.index?.zone.name ?? "UTC"}
              zoneBasis={stream.index?.zone.basis}
              noun={{ one: "phone entry", many: "phone entries" }}
              globalKeys
              onFocusRow={setFocused}
              highlight={words.trim() ? { query: words.trim(), exact: false } : null}
              rowExtra={(row) => {
                const others = alsoOn(row)
                return others.length ? <span className="rounded border border-violet-400/60 px-1.5 text-[11px] text-violet-800 dark:text-violet-200">Also on {others.join(", ")}</span> : null
              }}
              className="h-[70dvh] flex-none @min-[62rem]:h-auto @min-[62rem]:min-h-[18rem] @min-[62rem]:flex-1"
            />
          )}
        </section>

        <div className="w-full border-t bg-card/60 md:max-w-[25rem] md:flex-[1_1_21rem] md:border-l md:border-t-0 @min-[62rem]:overflow-y-auto">
          <HomeRecordPanel caseId={caseId} row={focused} phoneIndex={phoneIndex} alsoOn={focused ? alsoOn(focused) : []} onThatDay={thatDay} />
        </div>
      </div>

      <ActivityStrip
        buckets={buckets.data ?? null}
        phoneIndex={phoneIndex}
        window={scope.window}
        onPick={(w) => carried.apply({ ...scope, window: w })}
        loading={buckets.isPending}
        error={buckets.isError ? "The weeks could not be counted; the list above is complete without them." : null}
      />
      {exporting && (
        <Suspense fallback={null}>
          <ExportDialog caseId={caseId} filter={filter} words={`the Phones page (${listWords})`} open={exporting} onOpenChange={setExporting} source="timeline_lens" />
        </Suspense>
      )}
    </div>
  )
}
