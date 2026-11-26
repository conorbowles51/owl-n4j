import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState, type FormEvent } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { failureText, revealValue } from "@/features/phones/api"
import { liveCollectClient } from "@/features/phones/collect.api"
import { useCollectTargets } from "@/features/phones/hooks/use-collect"
import { MentionMark } from "@/features/phones/mentions/MentionMark"
import { labelText } from "@/features/phones/lib/labels"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { LookInto } from "@/features/relations/LookInto"
import { PhoneShape } from "@/features/phones/ui/PhoneChip"
import { ScopeBar } from "@/features/phones/ui/ScopeBar"
import { useCasePhones } from "@/features/phones/ui/use-case-phones"
import { useUrlScope } from "@/features/phones/ui/use-phone-scope"
import { saveKeywordList, splitTerms } from "@/features/search/api"
import { hitLink } from "@/features/search/lib/hit-links"
import { hitPath } from "@/features/search/lib/open-hit"
import { recordPath } from "@/lib/record-links"
import { cn } from "@/lib/cn"
import { hitContext, searchPhones, searchPhonesElsewhere, searchPhonesKind, searchPhonesPeople, type KindCount, type NextStep, type PhoneHit, type PhoneSearchResult, type SavedDifferently } from "./api"
import { dayPath, stepPath, withElsewhere, withPeople, type StepScope } from "./step-path"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * Search every phone (Phones screen 2, headless/phones-redesign/Search.dc.html): one search across every part of
 * every phone in the scope, counted by kind and by phone, grouped with the matched text marked, the chosen hit opened
 * in context beside the list, people saved under different names on different phones, and ranked next steps.
 */
export default function PhoneSearchPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const q = (params.get("q") ?? "").trim()
  const exact = params.get("exact") === "1"
  const [typed, setTyped] = useState(q)
  useEffect(() => setTyped(q), [q])
  const scopeState = useUrlScope(caseId, { window: true })
  const { scope } = scopeState
  const phones = useCasePhones(caseId)
  const phoneIds = scope.phones.map((p) => p.id)
  const phoneKey = phoneIds.join(",")
  const from = scope.window?.from ?? null
  const to = scope.window?.to ?? null
  const search = useQuery({
    queryKey: ["phone-search", caseId, q, exact, phoneKey, from, to],
    queryFn: ({ signal }) => searchPhones(caseId, { q, exact, phones: phoneIds, from, to }, signal),
    enabled: !!caseId && !!q,
    retry: false,
    staleTime: 30_000,
  })
  const elsewhere = useQuery({
    queryKey: ["phone-search-elsewhere", caseId, q, exact],
    queryFn: ({ signal }) => searchPhonesElsewhere(caseId, q, exact, signal),
    enabled: !!caseId && !!q && !!search.data && search.data.total > 0,
    retry: false,
    staleTime: 60_000,
  })
  const people = useQuery({
    queryKey: ["phone-search-people", caseId, q, exact, phoneKey],
    queryFn: ({ signal }) => searchPhonesPeople(caseId, { q, exact, phones: phoneIds }, signal),
    enabled: !!caseId && !!q && !!search.data?.people_pending,
    retry: false,
    staleTime: 30_000,
  })
  const [picked, setPicked] = useState<PhoneHit | null>(null)
  const [openKind, setOpenKind] = useState<{ kind: string; phone: string | null } | null>(null)
  useEffect(() => {
    setPicked(null)
    setOpenKind(null)
  }, [q, exact, phoneKey, from, to])
  const data = search.data
  useEffect(() => {
    if (data && !picked) setPicked(data.groups[0]?.items[0] ?? null)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the first hit of a new result
  }, [data])
  const indexOf = useMemo(() => new Map(phones.map((p) => [p.id, p.index])), [phones])
  const stepScope: StepScope = { phones: phoneIds, from, to }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setParams((p) => {
      const next = new URLSearchParams(p)
      if (typed.trim()) next.set("q", typed.trim())
      else next.delete("q")
      return next
    })
  }
  const setExact = (on: boolean) =>
    setParams((p) => {
      const next = new URLSearchParams(p)
      if (on) next.set("exact", "1")
      else next.delete("exact")
      return next
    }, { replace: true })

  return (
    <div className="flex h-full flex-col overflow-auto bg-background text-foreground" data-testid="phone-search">
      <header className="flex flex-col gap-3 border-b px-4 py-4 md:px-6">
        <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
          <Link to={`/cases/${encodeURIComponent(caseId)}/phones`} className="hover:underline">Phones</Link> / Search
        </nav>
        <h1 className="text-xl font-semibold">Search every phone</h1>
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" role="search">
          <label htmlFor="phone-search-q" className="sr-only">Search every phone</label>
          <input
            id="phone-search-q"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="A name, a number, an email address or a word"
            className="h-9 flex-1 rounded-md border bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            autoFocus={!q}
          />
          <Button type="submit" disabled={!typed.trim()}>Search</Button>
        </form>
        <ScopeBar
          scope={scope}
          onChange={scopeState.apply}
          presets={scopeState.presets}
          recent={scopeState.recent}
          restored={scopeState.restored}
          notApplied={scopeState.notApplied}
          count={data ? { shown: data.total, total: data.total, noun: data.total === 1 ? "result" : "results" } : null}
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>Names, numbers in any format, email addresses, account names and words, in every field of every record. Deleted items included.</span>
          <label className="inline-flex items-center gap-1.5 text-foreground">
            <input type="checkbox" checked={exact} onChange={(e) => setExact(e.target.checked)} />
            Exact characters
          </label>
        </div>
      </header>

      {!q && <p className="px-4 py-6 text-sm text-muted-foreground md:px-6">Type what you are looking for and press Search. Every phone in the case is searched unless you take one off the scope.</p>}
      {q && search.isLoading && <p role="status" className="px-4 py-6 text-sm md:px-6">Searching every phone for “{q}”</p>}
      {q && search.isError && (
        <div role="alert" className="flex flex-col items-start gap-2 px-4 py-6 text-sm md:px-6">
          <p>{failureText(search.error, "The search could not be run.")} Nothing was searched.</p>
          <Button variant="outline" size="sm" onClick={() => search.refetch()}>Try again</Button>
        </div>
      )}
      {data && (
        <Results
          caseId={caseId}
          data={data}
          exact={exact}
          indexOf={indexOf}
          picked={picked}
          onPick={setPicked}
          openKind={openKind}
          onOpenKind={setOpenKind}
          stepScope={stepScope}
          elsewhereStep={elsewhere.data?.step ?? null}
          elsewhereLoading={elsewhere.isLoading}
          saved={data.people_pending ? (people.data?.saved_differently ?? []) : data.saved_differently}
          personSteps={data.people_pending ? (people.data?.steps ?? []) : []}
          peopleLoading={!!data.people_pending && people.isLoading}
        />
      )}
    </div>
  )
}

function Results({ caseId, data, exact, indexOf, picked, onPick, openKind, onOpenKind, stepScope, elsewhereStep, elsewhereLoading, saved, personSteps, peopleLoading }: {
  caseId: string
  data: PhoneSearchResult
  exact: boolean
  indexOf: Map<string, number>
  picked: PhoneHit | null
  onPick: (h: PhoneHit) => void
  openKind: { kind: string; phone: string | null } | null
  onOpenKind: (k: { kind: string; phone: string | null } | null) => void
  stepScope: StepScope
  elsewhereStep: NextStep | null
  elsewhereLoading: boolean
  saved: SavedDifferently[]
  personSteps: NextStep[]
  peopleLoading: boolean
}) {
  const found = data.kinds.filter((k) => k.total > 0)
  const phoneCount = data.phones.length
  const steps = useMemo(() => withElsewhere(withPeople(data.next_steps, personSteps), elsewhereStep), [data.next_steps, personSteps, elsewhereStep])
  if (data.short) return <p role="status" className="px-4 py-6 text-sm md:px-6">{data.short} Shorter text is matched against numbers and identifiers only.</p>
  return (
    <div className="flex flex-col gap-4 px-4 py-4 md:px-6">
      {data.limits.map((l) => (
        <p key={l.message} role="alert" className="rounded-md border border-status-review bg-status-review-soft px-3 py-2 text-sm">{l.message}</p>
      ))}
      <div>
        <p className="text-lg font-semibold" role="status">
          {n(data.total)} {data.total === 1 ? "result" : "results"}
        </p>
        <p className="text-sm text-muted-foreground">
          {data.total === 0
            ? `Nothing on ${phoneCount === 1 ? "this phone" : `these ${phoneCount} phones`} matches “${data.query}”. Check the spelling, try part of the word, or take a phone or the dates off the scope.`
            : `on ${phoneCount === 1 ? "1 phone" : `${phoneCount === phoneCountAll(indexOf) ? "all " : ""}${phoneCount} phones`}, in ${found.length} ${found.length === 1 ? "kind" : "kinds"} of record${data.number_digits ? `. A number: every way of writing ${data.number_digits} is searched` : ""}`}
        </p>
      </div>
      {data.total > 0 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="flex min-w-0 flex-col gap-4">
            <KindTable caseId={caseId} data={data} found={found} indexOf={indexOf} onOpen={onOpenKind} />
            {saved.map((s) => (
              <section key={s.identity_keys.join(",")} aria-label="Saved differently" className="rounded-lg border bg-card p-3 text-sm">
                <p className="font-semibold">{s.name} is saved differently on each phone</p>
                <p className="mt-1 text-muted-foreground">{s.sentence}</p>
                <Link className="mt-2 inline-block font-medium text-foreground underline underline-offset-2" to={stepPath(caseId, { id: "person", title: "", why: "", open: { screen: "person", params: { people: s.identity_keys.join(","), person_id: s.person_id } } }, stepScope)}>
                  Open {s.name} across every phone
                </Link>
              </section>
            ))}
            {openKind ? (
              <KindList caseId={caseId} data={data} exact={exact} kind={openKind.kind} phone={openKind.phone} indexOf={indexOf} picked={picked} onPick={onPick} onClose={() => onOpenKind(null)} stepScope={stepScope} />
            ) : (
              data.groups.map((g) => (
                <section key={g.kind} aria-label={g.label} className="rounded-lg border bg-card">
                  <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
                    <h2 className="text-sm font-semibold">{g.label} · {n(g.total)}</h2>
                    {g.total > g.items.length && (
                      <button type="button" className="text-sm font-medium text-foreground underline underline-offset-2 hover:no-underline" onClick={() => onOpenKind({ kind: g.kind, phone: null })}>
                        Show all {n(g.total)}
                      </button>
                    )}
                  </div>
                  <ul>
                    {g.items.map((h, i) => (
                      <HitRow key={`${g.kind}-${i}`} hit={h} index={indexOf.get(h.extraction_id ?? "") ?? 0} selected={same(picked, h)} onPick={onPick} />
                    ))}
                  </ul>
                </section>
              ))
            )}
          </div>
          <div className="min-w-0 lg:sticky lg:top-0 lg:self-start">
            {picked && <ContextPane caseId={caseId} hit={picked} q={data.query} exact={exact} index={indexOf.get(picked.extraction_id ?? "") ?? 0} stepScope={stepScope} />}
          </div>
        </div>
      )}
      <NextSteps caseId={caseId} steps={steps} q={data.query} exact={exact} stepScope={stepScope} waiting={[...(peopleLoading ? ["Checking whether the people found are saved under different names on each phone"] : []), ...(elsewhereLoading ? ["Checking the case's documents and payments for the same words"] : [])]} />
    </div>
  )
}

function phoneCountAll(indexOf: Map<string, number>) {
  return indexOf.size
}

function same(a: PhoneHit | null, b: PhoneHit) {
  return !!a && (a.event_uid ?? a.record_uid ?? a.file_uid) === (b.event_uid ?? b.record_uid ?? b.file_uid)
}

function KindTable({ caseId, data, found, indexOf, onOpen }: {
  caseId: string
  data: PhoneSearchResult
  found: KindCount[]
  indexOf: Map<string, number>
  onOpen: (k: { kind: string; phone: string | null }) => void
}) {
  void caseId
  return (
    <section aria-label="Results by kind and phone" className="rounded-lg border bg-card">
      <h2 className="border-b px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Results by kind and phone</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              {/* the kind and its total stay in view while the phone columns scroll (14 phones at 1440 hid All) */}
              <th scope="col" className="sticky left-0 z-10 bg-card px-3 py-2 font-medium">Found in</th>
              {data.phones.map((p) => (
                <th key={p.extraction_id} scope="col" className="px-3 py-2 text-right font-medium">
                  <span className="inline-flex items-center gap-1.5"><PhoneShape index={indexOf.get(p.extraction_id) ?? 0} />{p.label}</span>
                </th>
              ))}
              <th scope="col" className="sticky right-0 z-10 border-l bg-card px-3 py-2 text-right font-medium">All</th>
            </tr>
          </thead>
          <tbody>
            {found.map((k) => (
              <tr key={k.kind} className="border-t">
                <th scope="row" className="sticky left-0 z-10 bg-card px-3 py-1.5 text-left font-medium">{k.label}{k.deleted ? <span className="ml-1 text-xs font-normal text-muted-foreground">({n(k.deleted)} deleted)</span> : null}</th>
                {data.phones.map((p) => {
                  const v = k.by_phone[p.extraction_id] ?? 0
                  return (
                    <td key={p.extraction_id} className="px-3 py-1.5 text-right tabular-nums">
                      {v ? (
                        <button type="button" className="font-medium text-foreground underline underline-offset-2 hover:no-underline" aria-label={`${n(v)} ${k.label.toLowerCase()} on ${p.label}`} onClick={() => onOpen({ kind: k.kind, phone: p.extraction_id })}>{n(v)}</button>
                      ) : (
                        <span className="text-muted-foreground" aria-label={`none on ${p.label}`}>·</span>
                      )}
                    </td>
                  )
                })}
                <td className="sticky right-0 z-10 border-l bg-card px-3 py-1.5 text-right tabular-nums">
                  <button type="button" className="font-semibold text-foreground underline underline-offset-2 hover:no-underline" aria-label={`All ${n(k.total)} ${k.label.toLowerCase()}`} onClick={() => onOpen({ kind: k.kind, phone: null })}>{n(k.total)}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Snippet({ hit }: { hit: PhoneHit }) {
  const s = hit.snippet
  if (!s) return <span className="text-muted-foreground">No text to show</span>
  return (
    <span className="break-words">
      {s.before}
      {s.match && <mark className="rounded-sm bg-status-review-soft px-0.5 font-medium text-foreground">{s.match}</mark>}
      {s.after}
    </span>
  )
}

function hitWhere(h: PhoneHit) {
  if (h.thread_title) return `${h.kind === "call" ? "Call" : h.kind === "email" ? "Email" : "Messages"} with ${h.thread_title}`
  return h.where ?? h.title
}

function HitRow({ hit, index, selected, onPick }: { hit: PhoneHit; index: number; selected: boolean; onPick: (h: PhoneHit) => void }) {
  const { id: caseId } = useParams()
  return (
    <li className={cn("border-b last:border-b-0", selected && "bg-accent")}>
      <button type="button" className="flex w-full gap-3 px-3 py-2.5 text-left text-sm hover:bg-accent/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-pressed={selected} onClick={() => onPick(hit)}>
        <PhoneShape index={index} className="mt-0.5" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">{hit.phone_label}</span>
            <span>{hitWhere(hit)}</span>
            {hit.time && <span>{hit.time}</span>}
            {hit.deleted && <span className="rounded-sm border px-1 font-medium text-foreground">Deleted</span>}
            {hit.masked && <span className="rounded-sm border px-1 font-medium text-foreground">Hidden value</span>}
          </span>
          <Snippet hit={hit} />
        </span>
      </button>
      {hit.record_uid && <MentionMark caseId={caseId} recordUid={hit.record_uid} className="px-3 pb-2 pl-10" />}
    </li>
  )
}

function KindList({ caseId, data, exact, kind, phone, indexOf, picked, onPick, onClose, stepScope }: {
  caseId: string
  data: PhoneSearchResult
  exact: boolean
  kind: string
  phone: string | null
  indexOf: Map<string, number>
  picked: PhoneHit | null
  onPick: (h: PhoneHit) => void
  onClose: () => void
  stepScope: StepScope
}) {
  const phones = phone ? [phone] : stepScope.phones
  const [pages, setPages] = useState<number>(1)
  const list = useQuery({
    queryKey: ["phone-search-kind", caseId, data.query, exact, kind, phones.join(","), stepScope.from, stepScope.to, pages],
    queryFn: async ({ signal }) => {
      const items: PhoneHit[] = []
      let cursor: string | null = null
      let total = 0
      for (let i = 0; i < pages; i++) {
        const page = await searchPhonesKind(caseId, { q: data.query, exact, phones, from: stepScope.from, to: stepScope.to }, kind, cursor, signal)
        items.push(...page.items)
        total = page.total
        cursor = page.next_cursor
        if (!cursor) break
      }
      return { items, total, more: !!cursor }
    },
    retry: false,
  })
  const label = data.kinds.find((k) => k.kind === kind)?.label ?? kind
  const phoneLabel = phone ? data.phones.find((p) => p.extraction_id === phone)?.label : null
  return (
    <section aria-label={`${label}, every result`} className="rounded-lg border bg-card">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 className="text-sm font-semibold">
          {label}{phoneLabel ? ` on ${phoneLabel}` : ""}{list.data ? ` · ${n(list.data.total)}` : ""}
        </h2>
        <button type="button" className="text-sm font-medium text-foreground underline underline-offset-2 hover:no-underline" onClick={onClose}>Back to every kind</button>
      </div>
      {list.isLoading && <p role="status" className="px-3 py-2 text-sm">Reading every result</p>}
      {list.isError && <p role="alert" className="px-3 py-2 text-sm">{failureText(list.error, "These results could not be read.")}</p>}
      {list.data && (
        <>
          <p className="px-3 pt-2 text-xs text-muted-foreground" role="status">
            Showing {n(list.data.items.length)} of {n(list.data.total)}{list.data.more ? ", 200 more with each press of Show more" : ""}.
          </p>
          <ul>
            {list.data.items.map((h, i) => (
              <HitRow key={`${kind}-${i}`} hit={h} index={indexOf.get(h.extraction_id ?? "") ?? 0} selected={same(picked, h)} onPick={onPick} />
            ))}
          </ul>
          {list.data.more && (
            <div className="px-3 py-2"><Button variant="outline" size="sm" onClick={() => setPages((p) => p + 1)}>Show more</Button></div>
          )}
        </>
      )}
    </section>
  )
}

function ContextPane({ caseId, hit, q, exact, index, stepScope }: { caseId: string; hit: PhoneHit; q: string; exact: boolean; index: number; stepScope: StepScope }) {
  const isComm = !!hit.event_uid
  const ctx = useQuery({
    queryKey: ["phone-search-context", caseId, hit.event_uid],
    queryFn: ({ signal }) => hitContext(caseId, hit.event_uid!, signal),
    enabled: isComm,
    retry: false,
    staleTime: 60_000,
  })
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const collect = useCollectTargets(caseId)
  const link = hitLink(hit, q)
  const day = ctx.data?.day ?? hit.day ?? null
  return (
    <section aria-label="In context" className="flex flex-col rounded-lg border bg-card">
      <div className="border-b px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">In context</p>
        <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
          <PhoneShape index={index} />
          {hit.phone_label} · {hitWhere(hit)}
        </p>
        {isComm && ctx.data && (
          <p className="text-xs text-muted-foreground">
            {ctx.data.thread_count != null ? `${n(ctx.data.thread_count)} ${ctx.data.thread_count === 1 ? "item" : "items"} in this conversation` : ctx.data.note}
            {ctx.data.deleted ? " · this one is deleted, recovered from the phone" : ""}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2 px-3 py-3 text-sm">
        {isComm && ctx.isLoading && <p role="status">Reading the conversation</p>}
        {isComm && ctx.isError && <p role="alert">{failureText(ctx.error, "The conversation could not be read.")} Open the thread to read it in full.</p>}
        {isComm && ctx.data?.items.map((r) => {
          const mine = r.from?.is_owner
          const isHit = r.event_uid === hit.event_uid
          return (
            <div key={r.event_uid} className={cn("flex max-w-[85%] flex-col gap-0.5 rounded-lg border px-3 py-2", mine ? "self-end bg-muted" : "self-start bg-background", isHit && "border-2 border-foreground")} aria-current={isHit ? "true" : undefined}>
              {/* muted text on the owner's muted bubble was 4.49:1 in light (live, Phone reference 1) */}
              <span className={cn("text-xs", mine ? "text-foreground" : "text-muted-foreground")}>
                {labelText(r.from)} · {r.time.row}{r.flags.includes("deleted") ? " · deleted, recovered from the phone" : ""}
              </span>
              <span className="break-words">{isHit ? <Snippet hit={{ ...hit, snippet: hit.snippet && r.body && r.body.includes(hit.snippet.match) ? splitAt(r.body, hit.snippet.match) : hit.snippet }} /> : (r.body ?? r.call?.words ?? r.subject ?? "(no text)")}</span>
            </div>
          )
        })}
        {!isComm && <RecordContext caseId={caseId} hit={hit} />}
      </div>
      <div className="flex flex-wrap gap-2 border-t px-3 py-2">
        {link && (
          <AddToMenu
            caseId={caseId}
            links={[link]}
            noun="result"
            targets={collect.data ?? []}
            client={liveCollectClient}
            origin="Added from Search every phone"
            label="Add to the case"
            corroborate={false}
            keys={false}
            disabledReason={canEdit ? undefined : "A case member who can edit can add."}
          />
        )}
        <Button asChild variant="outline" size="sm">
          <Link to={hit.open.screen === "record" ? recordPath(caseId, String(hit.record_uid)) : hitPath(caseId, hit)}>{isComm ? "Open the thread" : "Open the record"}</Link>
        </Button>
        {day && (
          <Button asChild variant="outline" size="sm">
            <Link to={dayPath(caseId, day)}>That day, all phones</Link>
          </Button>
        )}
        {link && canEdit ? (
          // this hit itself on the Corroborate page (lx-corroredo), last as in the design
          <LookInto caseId={caseId} surface="phone" items={[{ target_type: link.target_type, target_id: link.target_id, target_label: link.label }]} />
        ) : (
          <Button asChild variant="outline" size="sm">
            <Link to={stepPath(caseId, { id: "corroborate", title: "", why: "", open: { screen: "corroborate", params: { q } } }, stepScope, exact)}>Corroborate</Link>
          </Button>
        )}
      </div>
    </section>
  )
}

function splitAt(body: string, match: string) {
  const at = body.indexOf(match)
  return { before: body.slice(0, at), match, after: body.slice(at + match.length) }
}

function RecordContext({ caseId, hit }: { caseId: string; hit: PhoneHit }) {
  const [shown, setShown] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setShown(null)
    setErr(null)
  }, [hit.record_uid, hit.file_uid])
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">{hit.where ?? hit.title}{hit.time ? ` · ${hit.time}` : ""}{hit.folder ? ` · in ${hit.folder}` : ""}</p>
      <p className="break-words"><Snippet hit={hit} /></p>
      {hit.masked && hit.record_uid && hit.field_path && (
        <div className="flex flex-col items-start gap-1">
          {shown != null ? (
            <p className="rounded-md border px-2 py-1 font-mono text-sm">{shown}</p>
          ) : (
            <Button variant="outline" size="sm" onClick={() => revealValue(caseId, hit.record_uid!, hit.field_path!, hit.value_index ?? 0).then((r: { value?: string }) => setShown(r.value ?? "")).catch((e) => setErr(failureText(e, "The value could not be revealed.")))}>
              Reveal (logged)
            </Button>
          )}
          <p className="text-xs text-muted-foreground">A hidden value is shown only when you reveal it, and each reveal is logged with your name.</p>
          {err && <p role="alert" className="text-xs">{err}</p>}
        </div>
      )}
    </div>
  )
}

function NextSteps({ caseId, steps, q, exact, stepScope, waiting }: { caseId: string; steps: NextStep[]; q: string; exact: boolean; stepScope: StepScope; waiting: string[] }) {
  const [saved, setSaved] = useState<string | null>(null)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  if (!steps.length && !waiting.length) return null
  return (
    <section aria-label="Next steps" className="rounded-lg border bg-card">
      <h2 className="border-b px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Next steps</h2>
      <ol className="divide-y">
        {steps.map((s) => (
          <li key={s.id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 gap-3">
              <span className="mt-0.5 text-sm font-semibold tabular-nums text-muted-foreground">{s.rank}</span>
              <div className="min-w-0">
                <p className="text-sm font-semibold">{s.title}</p>
                <p className="text-sm text-muted-foreground">{s.why}</p>
              </div>
            </div>
            {s.id === "keyword_list" ? (
              saved ? (
                <Link className="shrink-0 text-sm font-medium text-foreground underline underline-offset-2 hover:no-underline" to={stepPath(caseId, s, stepScope, exact)}>{saved}</Link>
              ) : (
                <Button variant="outline" size="sm" className="shrink-0" onClick={() => saveKeywordList(caseId, q, splitTerms(q), exact).then(() => setSaved("Saved: open the keyword lists")).catch((e) => setSaveErr(failureText(e, "The keyword list could not be saved.")))}>
                  Save as a keyword list
                </Button>
              )
            ) : (
              <Button asChild variant="outline" size="sm" className="shrink-0">
                <Link to={stepPath(caseId, s, stepScope, exact)}>{stepButton(s)}</Link>
              </Button>
            )}
          </li>
        ))}
        {waiting.map((w) => <li key={w} className="px-3 py-2 text-xs text-muted-foreground" role="status">{w}</li>)}
      </ol>
      {saveErr && <p role="alert" className="px-3 pb-2 text-xs">{saveErr}</p>}
    </section>
  )
}

function stepButton(s: NextStep) {
  switch (s.open.screen) {
    case "person": return "Open the person"
    case "conversations": return "Open them"
    case "corroborate": return "See them"
    case "timeline": return "Open the timeline"
    case "ask": return "Ask"
    case "phones": return "See the phones"
    default: return "Open"
  }
}
