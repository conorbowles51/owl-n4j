import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useCase } from "@/features/cases/hooks/use-cases"
import { installKeymap, register } from "@/lib/keymap"
import {
  failureText,
  freezeSelection,
  getSelection,
  getParticipants,
  getPhones,
  getSettings,
  getThreads,
  markNotACopy,
  markReviewed,
  undoReviewed,
  type ThreadSort,
  streamLocate,
} from "@/features/phones/api"
import { liveCollectClient, undoCollect, type CollectLink, type CollectResult, type CollectTarget } from "@/features/phones/collect.api"
import { PhoneRecordPanel } from "@/features/phones/components/RecordPanel"
import { StreamList } from "@/features/phones/components/StreamList"
import { useCollectTargets, useUsedIn } from "@/features/phones/hooks/use-collect"
import { useStream } from "@/features/phones/hooks/use-stream"
import { ExportDialog } from "./ExportDialog"
import { PersonScope } from "./PersonScope"
import { useThreadMatches } from "./use-thread-matches"
import { viewFromSearch, viewToFilter, viewToSearch, type ConversationView } from "@/features/phones/lib/filter-url"
import { rememberSpot } from "@/features/phones/lib/continue-reading"
import { labelText } from "@/features/phones/lib/labels"
import type { StreamRow, ThreadRow } from "@/features/phones/schemas"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { fmt } from "@/features/phones/ui/ResultCount"
import { EMPTY_SCOPE, ScopeBar, type Scope } from "@/features/phones/ui/ScopeBar"
import { TimeStrip, type StripDay } from "@/features/phones/ui/TimeStrip"

/**
 * Conversations (03 section 6; 07 sections 5 and 6.1): the threads of the case's phones, or the people in them, on
 * the left; the chosen thread or person's messages in the one stream list on the right, with the scope in words,
 * the time strip and the record panel. Every filter lives in the URL (filter-url.ts), so any view is linkable and
 * Back returns to it. The first thread opens on arrival (D-38), so the keys act at once.
 *
 * Keys: j/k move, Space selects, r opens the record, a shows what else happened around the focused message, m marks
 * the thread reviewed (with Undo), c then d/w/n/t/l adds the selection to a dossier, finding, note, Timeline or
 * label. Ctrl/Cmd+A selects the whole result; Add to… then adds it as one frozen selection, so nothing in it is
 * silently left out.
 */

const SORT_WORDS: Record<ThreadSort, string> = {
  recent: "Most recent first",
  first: "Earliest first",
  volume: "Most messages first",
  unreviewed: "Not yet reviewed first",
  name: "By name",
}
const AROUND_MINUTES = 60
const SELECTION_AS_ONE = 500

function daysOf(items: { day: string; count: number }[]): StripDay[] {
  if (!items.length) return []
  const sorted = [...items].sort((a, b) => a.day.localeCompare(b.day))
  const byDay = new Map(sorted.map((d) => [d.day, d.count]))
  const out: StripDay[] = []
  const end = new Date(`${sorted[sorted.length - 1].day}T00:00:00Z`)
  for (let d = new Date(`${sorted[0].day}T00:00:00Z`); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const key = d.toISOString().slice(0, 10)
    out.push({ date: key, count: byDay.get(key) ?? 0 })
    if (out.length > 3660) break // ten years of days; the index covers the rest
  }
  return out
}

export function ConversationsPage() {
  const { id: caseId = "", extraction } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const fixedPhone = extraction ?? null
  const view = useMemo(() => viewFromSearch(location.search, fixedPhone), [location.search, fixedPhone])
  const setView = useCallback(
    (patch: Partial<ConversationView>, replace = false) => {
      const next = { ...view, ...patch }
      navigate({ pathname: location.pathname, search: viewToSearch(next, fixedPhone) }, { replace })
    },
    [view, navigate, location.pathname, fixedPhone],
  )

  const caseQ = useCase(caseId)
  const savedQ = useQuery({
    queryKey: ["phone-selection", caseId, view.selection],
    queryFn: () => getSelection(caseId, view.selection!),
    enabled: !!caseId && !!view.selection,
    staleTime: Infinity,
    retry: false,
  })
  const phonesQ = useQuery({ queryKey: ["phones", caseId], queryFn: () => getPhones(caseId), enabled: !!caseId })
  const settingsQ = useQuery({ queryKey: ["phone-settings", caseId], queryFn: () => getSettings(caseId), enabled: !!caseId })
  const zoneName = settingsQ.data?.effective.name ?? "UTC"

  const listFilter = useMemo(() => viewToFilter(caseId, view, zoneName, false), [caseId, view, zoneName])
  const threadsQ = useQuery({
    queryKey: ["phone-threads", listFilter, view.threadSort],
    queryFn: () => getThreads(listFilter, view.threadSort),
    enabled: !!caseId && settingsQ.isSuccess,
  })
  const peopleQ = useQuery({
    queryKey: ["phone-people", listFilter],
    queryFn: () => getParticipants(listFilter),
    enabled: !!caseId && settingsQ.isSuccess && (view.tab === "people" || view.people.length > 0),
  })
  const threads = useMemo(() => threadsQ.data?.items ?? [], [threadsQ.data])

  // D-38: the first thread opens on arrival, so j, r, m and c act at once (07 J-8b, J-12, J-13).
  useEffect(() => {
    if (view.tab === "threads" && !view.thread && !view.record && threads.length) setView({ thread: threads[0].thread_key }, true)
  }, [view.tab, view.thread, view.record, threads, setView])

  // A link to one record (?record=) reads every message of the phones in scope with that record open beside it.
  const ready = view.tab === "threads" ? !!view.thread || !!view.record : view.people.length > 0
  const streamFilter = useMemo(() => (ready && settingsQ.isSuccess ? viewToFilter(caseId, view, zoneName, true) : null), [ready, settingsQ.isSuccess, caseId, view, zoneName])
  const stream = useStream(streamFilter)

  const [find, setFind] = useState("")
  const shownThreads = useMemo(() => {
    const q = find.trim().toLowerCase()
    if (!q) return threads
    return threads.filter((t) => `${t.title} ${t.app ?? ""} ${t.participants.map(labelText).join(" ")}`.toLowerCase().includes(q))
  }, [threads, find])
  const multiPhone = new Set(threads.map((t) => t.phone.extraction_id)).size > 1
  const current: ThreadRow | undefined = threads.find((t) => t.thread_key === view.thread)
  // Continue reading on the Phone summary (07 J-15): the threads opened here, on this browser.
  useEffect(() => {
    if (current) rememberSpot(caseId, { thread: current.thread_key, title: current.title, phone: current.phone.label, extraction: current.phone.extraction_id, at: new Date().toISOString() })
  }, [caseId, current])

  // ---- record panel, focus, selection --------------------------------------------------------------------------
  const [recordUid, setRecordUid] = useState<string | null>(view.record)
  const [focused, setFocused] = useState<StreamRow | null>(null)
  const [selection, setSelection] = useState<{ rows: StreamRow[]; all: boolean }>({ rows: [], all: false })
  const onSelectionChange = useCallback((rows: StreamRow[], all: boolean) => setSelection({ rows, all }), [])
  const [exporting, setExporting] = useState(false)
  const [jump, setJump] = useState<{ day: string | null; seq: number; offset?: number } | null>(null)
  const listRoot = useRef<HTMLDivElement>(null)

  // ---- a search hit: the whole thread, its matches marked, stepped through (03 S-8) -------------------------------
  const matches = useThreadMatches(view.hl && view.thread ? streamFilter : null, view.hl, view.hlExact)
  const [matchAt, setMatchAt] = useState(0)
  const goTo = useCallback(
    async (eventUid: string) => {
      if (!streamFilter || !stream.index) return
      try {
        const loc = await streamLocate(streamFilter, stream.index.snapshot, eventUid)
        setJump({ day: loc.day, offset: loc.offset, seq: Date.now() })
      } catch {
        /* the message left the list (a stale snapshot re-reads it); the list stays where it is */
      }
    },
    [streamFilter, stream.index],
  )
  const arrivedAt = useRef<string | null>(null)
  useEffect(() => {
    // open at the hit's message once the list is ready
    if (!view.at || !streamFilter || !stream.index || arrivedAt.current === view.at) return
    arrivedAt.current = view.at
    void goTo(view.at)
  }, [view.at, streamFilter, stream.index, goTo])
  useEffect(() => {
    if (view.at && matches.data) setMatchAt(Math.max(0, matches.data.events.indexOf(view.at)))
  }, [view.at, matches.data])
  const stepMatch = (dir: 1 | -1) => {
    const ev = matches.data?.events ?? []
    if (!ev.length) return
    const next = (matchAt + dir + ev.length) % ev.length
    setMatchAt(next)
    void goTo(ev[next])
  }

  // ---- Add to… ---------------------------------------------------------------------------------------------------
  const targets = useCollectTargets(caseId)
  const visibleUids = useMemo(() => {
    const out: string[] = []
    for (let i = 0; i < stream.count && out.length < 400; i++) {
      const it = stream.item(i)
      if (it.type === "row" && it.row) out.push(it.row.record_uid)
    }
    return out
  }, [stream])
  const { usedIn, refresh: refreshUsedIn } = useUsedIn(caseId, visibleUids)
  const filterWords = current ? `${current.title} on ${current.phone.label}` : view.people.length ? "Messages with the chosen people" : "Conversations"
  const freeze = useQuery({
    queryKey: ["phone-selection", streamFilter, selection.all],
    queryFn: () => freezeSelection(streamFilter!, `${filterWords}, every message`),
    enabled: !!streamFilter && selection.all && stream.total > SELECTION_AS_ONE,
    staleTime: Infinity,
    retry: false,
  })
  const links: CollectLink[] = useMemo(() => {
    if (selection.all && stream.total > SELECTION_AS_ONE) {
      return freeze.data ? [{ target_type: "phone_selection", target_id: freeze.data.id, label: freeze.data.words, source_anchor: { origin: "conversations" } }] : []
    }
    // Every copy of a row found more than once goes in, as the frozen selection does (review of 03-3).
    const out: CollectLink[] = []
    const seen = new Set<string>()
    for (const r of selection.rows) {
      for (const uid of [r.record_uid, ...r.copies.record_uids]) {
        if (seen.has(uid)) continue
        seen.add(uid)
        out.push({ target_type: "phone_record", target_id: uid, label: r.line, source_anchor: { event_uid: r.event_uid, thread_key: r.thread?.thread_key ?? null } })
      }
    }
    return out
  }, [selection, stream.total, freeze.data])
  // A message found more than once adds each copy as its own record, so the count then names records (review of D).
  const addNoun = selection.all && stream.total > SELECTION_AS_ONE ? "selection" : links.length > selection.rows.length ? "records (messages and their copies)" : "messages"
  const addDisabled = selection.all && stream.total > SELECTION_AS_ONE && freeze.isError ? failureText(freeze.error, "The whole result could not be prepared for adding.") : undefined
  const onAdded = useCallback(() => void refreshUsedIn(), [refreshUsedIn])
  const [undoNote, setUndoNote] = useState<string | null>(null)
  const onUndoAdd = useCallback(
    (target: CollectTarget, result: CollectResult) => {
      setUndoNote("Undoing the add")
      undoCollect(caseId, target, result)
        .then((n) => setUndoNote(`Undone: removed ${fmt(n)} ${n === 1 ? "link" : "links"} from ${target.label}.`))
        .catch((e) => setUndoNote(e instanceof Error ? e.message : "The undo failed. Nothing more was removed."))
        .finally(() => void refreshUsedIn())
    },
    [caseId, refreshUsedIn],
  )

  // ---- review marks ----------------------------------------------------------------------------------------------
  const [reviewNote, setReviewNote] = useState<{ thread: string; text: string } | null>(null)
  // A second m before the first answer would store two marks; the key waits for the answer (review of 03-3).
  const reviewBusy = useRef(false)
  const review = useMutation({
    onMutate: () => {
      reviewBusy.current = true
    },
    onSettled: () => {
      reviewBusy.current = false
    },
    mutationFn: async ({ thread, undo }: { thread: string; undo: boolean }): Promise<void> => {
      if (undo) await undoReviewed(caseId, thread)
      else await markReviewed(caseId, thread, { filter: viewToSearch(view, fixedPhone) })
    },
    onSuccess: (_r, v) => {
      setReviewNote(v.undo ? { thread: v.thread, text: "Review mark removed." } : { thread: v.thread, text: "Marked reviewed." })
      void qc.invalidateQueries({ queryKey: ["phone-threads"] })
    },
    onError: (e) => setReviewNote({ thread: view.thread ?? "", text: failureText(e, "The review mark could not be saved.") }),
  })

  // ---- Around this time -----------------------------------------------------------------------------------------
  const [around, setAround] = useState<StreamRow | null>(null)
  const aroundFilter = useMemo(() => {
    const at = around?.time.instant
    if (!at) return null
    const t = new Date(at).getTime()
    return {
      case_id: caseId,
      phones: view.phones.length ? view.phones : undefined,
      from_instant: new Date(t - AROUND_MINUTES * 60_000).toISOString(),
      to_instant: new Date(t + AROUND_MINUTES * 60_000).toISOString(),
      zone: { mode: view.zone, phone: null },
    }
  }, [around, caseId, view.phones, view.zone])
  const aroundQ = useQuery({ queryKey: ["phone-around", aroundFilter], queryFn: () => getThreads(aroundFilter!, "volume"), enabled: !!aroundFilter })

  // ---- Not a copy ------------------------------------------------------------------------------------------------
  const [copyRow, setCopyRow] = useState<StreamRow | null>(null)
  const [copyReason, setCopyReason] = useState("")
  const [copyNote, setCopyNote] = useState<{ recordUid: string; reason: string; text: string } | null>(null)
  const notCopy = useMutation({
    mutationFn: () => markNotACopy(caseId, copyRow!.record_uid, copyReason),
    onSuccess: () => {
      setCopyNote({ recordUid: copyRow!.record_uid, reason: copyReason, text: "Shown as its own message." })
      setCopyRow(null)
      setCopyReason("")
      stream.reload()
    },
  })
  const restoreCopy = useMutation({
    mutationFn: (n: { recordUid: string; reason: string }) => markNotACopy(caseId, n.recordUid, `Undo of: ${n.reason}`, true),
    onSuccess: () => {
      setCopyNote(null)
      stream.reload()
    },
    onError: (e) => setCopyNote((n) => (n ? { ...n, text: failureText(e, "The undo could not be saved.") } : n)),
  })

  // ---- keys ------------------------------------------------------------------------------------------------------
  const keyState = useRef({ focused, thread: view.thread, reviewed: !!current?.review })
  // Synced in the commit itself, so a key pressed right after a change acts on what is on screen.
  useLayoutEffect(() => {
    keyState.current = { focused, thread: view.thread, reviewed: !!current?.review }
  })
  useEffect(() => {
    installKeymap()
    return register("Conversations", [
      {
        key: "a",
        label: "Around this time",
        run: () => {
          const f = keyState.current.focused
          if (f?.time.instant) setAround(f)
        },
      },
      {
        key: "m",
        label: "Mark this thread reviewed",
        run: () => {
          const t = keyState.current.thread
          if (t && !reviewBusy.current) review.mutate({ thread: t, undo: false })
        },
      },
    ])
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the bindings read the latest state through keyState
  }, [])

  // ---- scope bar -------------------------------------------------------------------------------------------------
  const phones = useMemo(() => phonesQ.data?.phones ?? [], [phonesQ.data])
  const peopleByKey = useMemo(() => new Map((peopleQ.data?.items ?? []).map((p) => [p.label.identity_key ?? "", labelText(p.label)])), [peopleQ.data])
  const scope: Scope = {
    ...EMPTY_SCOPE,
    people: view.people.map((k) => ({ key: k, label: peopleByKey.get(k) ?? k })),
    mode: view.mode,
    phones: view.phones.map((id) => {
      const k = phones.findIndex((p) => p.extraction_id === id)
      return { id, label: phones[k]?.label ?? "A phone", index: Math.max(0, k) }
    }),
    window: view.from && view.to ? { from: view.from, to: view.to } : null,
    kinds: view.kinds,
  }
  const onScope = (s: Scope) =>
    setView({
      people: s.people.map((p) => p.key),
      mode: s.mode,
      phones: fixedPhone ? [fixedPhone] : s.phones.map((p) => p.id),
      from: s.window?.from ?? null,
      to: s.window?.to ?? null,
      kinds: s.kinds,
      thread: s.people.length ? null : view.thread,
      tab: s.people.length ? "people" : view.tab,
    })

  const counts = threadsQ.data?.counts
  const strip = useMemo(() => daysOf(stream.index?.items ?? []), [stream.index])

  if (phonesQ.isSuccess && phones.length === 0) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-semibold">Conversations</h1>
        <p className="mt-2 text-sm">This case has no phone yet. Add a phone report from Evidence to read its conversations here.</p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-baseline gap-3 border-b px-4 py-2">
        <h1 className="text-lg font-semibold">Conversations</h1>
        {view.selection && (
          // a saved link to a whole result opens on its frozen records, said as such (07 6.1)
          <p role="status" className="w-full text-sm" data-testid="saved-selection">
            {savedQ.isLoading && "Opening the saved selection"}
            {savedQ.isError && failureText(savedQ.error, "This saved selection could not be opened.")}
            {savedQ.data &&
              `Showing a saved selection: ${savedQ.data.words}. ${fmt(savedQ.data.event_count)} ${savedQ.data.event_count === 1 ? "message" : "messages"} as frozen${savedQ.data.created_at ? ` on ${new Date(savedQ.data.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}` : ""}; later messages are not added.`}{" "}
            {savedQ.data?.replaced && <span className="text-status-review">{savedQ.data.replaced}.</span>}{" "}
            <button type="button" className="underline underline-offset-2" onClick={() => setView({ selection: null })}>
              Show every message
            </button>
          </p>
        )}
        {counts && (
          <p className="text-sm" data-testid="not-reviewed">
            Not yet reviewed: {fmt(counts.not_reviewed ?? 0)} of {fmt(counts.threads ?? 0)} threads
          </p>
        )}
        {reviewNote && (
          <p role="status" className="text-sm">
            {reviewNote.text}{" "}
            {reviewNote.text === "Marked reviewed." && (
              <button type="button" className="underline underline-offset-2" onClick={() => review.mutate({ thread: reviewNote.thread, undo: true })}>
                Undo
              </button>
            )}
          </p>
        )}
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Threads and people" className="flex w-80 shrink-0 flex-col border-r bg-card">
          <div className="flex gap-1 border-b p-2" role="group" aria-label="List">
            <Button size="sm" variant={view.tab === "threads" ? "secondary" : "ghost"} aria-pressed={view.tab === "threads"} onClick={() => setView({ tab: "threads", people: [] })}>
              Threads
            </Button>
            <Button size="sm" variant={view.tab === "people" ? "secondary" : "ghost"} aria-pressed={view.tab === "people"} onClick={() => setView({ tab: "people", thread: null })}>
              People
            </Button>
          </div>
          {view.tab === "threads" ? (
            <>
              <div className="flex flex-col gap-1 border-b p-2 text-sm">
                <label className="text-xs font-medium" htmlFor="thread-find">
                  Find a thread
                </label>
                <input id="thread-find" className="rounded border bg-background px-2 py-1" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Name, number or app" />
                <label className="flex items-center gap-1 text-xs">
                  Order
                  <select className="rounded border bg-card px-1 py-0.5" value={view.threadSort} onChange={(e) => setView({ threadSort: e.target.value as ThreadSort })}>
                    {(Object.keys(SORT_WORDS) as ThreadSort[]).map((k) => (
                      <option key={k} value={k}>
                        {SORT_WORDS[k]}
                      </option>
                    ))}
                  </select>
                </label>
                {threadsQ.data && (
                  <p className="text-xs">
                    {shownThreads.length < threads.length ? `Showing ${fmt(shownThreads.length)} of ${fmt(threads.length)} threads` : `${fmt(threads.length)} threads`}
                  </p>
                )}
              </div>
              {threadsQ.isError && (
                <div role="alert" className="p-2 text-sm">
                  {failureText(threadsQ.error, "The conversation list could not be loaded.")}{" "}
                  <Button size="sm" variant="outline" onClick={() => void threadsQ.refetch()}>
                    Try again
                  </Button>
                </div>
              )}
              <ul role="listbox" aria-label={`Threads (${fmt(threads.length)})`} className="min-h-0 flex-1 overflow-auto">
                {shownThreads.map((t, k) => (
                  <li key={t.thread_key} role="presentation">
                    {multiPhone && (k === 0 || shownThreads[k - 1].phone.extraction_id !== t.phone.extraction_id) && view.threadSort === "name" && (
                      <p className="px-2 pt-2 text-xs font-semibold">{t.phone.label}</p>
                    )}
                    <div
                      role="option"
                      tabIndex={0}
                      aria-selected={t.thread_key === view.thread}
                      onClick={() => setView({ thread: t.thread_key, record: null })}
                      onKeyDown={(e) => e.key === "Enter" && setView({ thread: t.thread_key, record: null })}
                      className="cursor-pointer border-b px-2 py-1.5 text-sm hover:bg-muted aria-selected:bg-accent"
                    >
                      <span className="block truncate font-medium">{t.title}</span>
                      <span className="block text-xs text-muted-foreground">
                        {multiPhone ? `${t.phone.label} · ` : ""}
                        {t.app ?? "app not recorded"} · {fmt(t.event_count)} {t.event_count === 1 ? "message" : "messages"}
                        {t.deleted_count ? ` · ${fmt(t.deleted_count)} deleted` : ""}
                        {t.has_unreadable ? " · has unreadable content" : ""}
                      </span>
                      <span className="block text-xs">{t.review ? t.review.words : "Not yet reviewed"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <ul role="listbox" aria-label={`People (${fmt(peopleQ.data?.items.length ?? 0)})`} className="min-h-0 flex-1 overflow-auto">
              {peopleQ.isError && <li role="alert" className="p-2 text-sm">{failureText(peopleQ.error, "The list of people could not be loaded.")}</li>}
              {(peopleQ.data?.items ?? []).map((p) => {
                const key = p.label.identity_key
                return (
                  <li key={key ?? labelText(p.label)} role="presentation">
                    <div
                      role="option"
                      tabIndex={0}
                      aria-selected={!!key && view.people.includes(key)}
                      aria-disabled={!key}
                      onClick={() => key && setView({ people: [key], thread: null, record: null })}
                      onKeyDown={(e) => e.key === "Enter" && key && setView({ people: [key], thread: null, record: null })}
                      className="cursor-pointer border-b px-2 py-1.5 text-sm hover:bg-muted aria-selected:bg-accent"
                    >
                      <span className="block truncate font-medium">{labelText(p.label)}</span>
                      <span className="block text-xs text-muted-foreground">
                        {fmt(p.events)} {p.events === 1 ? "message" : "messages"} · {p.apps.join(", ") || "app not recorded"}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </nav>
        <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col" ref={listRoot}>
          <ScopeBar scope={scope} onChange={onScope} count={stream.status === "ready" && stream.index ? { shown: stream.total, total: stream.total, noun: "messages" } : null}>
            {view.people.length > 0 && (
              <PersonScope
                caseId={caseId}
                view={view}
                filter={streamFilter}
                names={scope.people.map((p) => p.label)}
                phonesTotal={phones.filter((p) => p.standing !== "superseded").length}
                counts={stream.index?.counts}
                setView={setView}
              />
            )}
          </ScopeBar>
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-1.5 text-sm">
            {current ? (
              <span className="font-medium">
                {current.title} on {current.phone.label}
                {current.app ? `, ${current.app}` : ""}
              </span>
            ) : null}
            {view.deleted === true && (
              // 07 J-11: a deletion state never carries a time; say what it does and does not establish.
              <span className="w-full text-xs">Deleted at some time between the message's own time and the extraction. The report does not record when.</span>
            )}
            {!current && view.tab === "people" && !view.people.length ? (
              <span>Pick a person to read every message with them.</span>
            ) : null}
            <span className="ml-auto flex flex-wrap items-center gap-1">
              <label className="inline-flex items-center gap-1 text-xs">
                <input type="checkbox" checked={view.everyCopy} onChange={(e) => setView({ everyCopy: e.target.checked })} />
                Show every copy
              </label>
              <Button size="sm" variant="outline" disabled={!streamFilter} onClick={() => setExporting(true)}>
                Export…
              </Button>
              {view.thread && (
                <Button size="sm" variant="outline" disabled={review.isPending} onClick={() => review.mutate({ thread: view.thread!, undo: false })}>
                  Mark reviewed <kbd className="ml-1 text-xs text-muted-foreground">m</kbd>
                </Button>
              )}
              <Button size="sm" variant="outline" disabled={!focused?.time.instant} onClick={() => focused && setAround(focused)}>
                Around this time <kbd className="ml-1 text-xs text-muted-foreground">a</kbd>
              </Button>
              <AddToMenu
                caseId={caseId}
                links={links}
                noun={addNoun}
                targets={targets.data ?? []}
                client={liveCollectClient}
                origin="Added from Conversations"
                onAdded={onAdded}
                onUndo={onUndoAdd}
                disabledReason={addDisabled}
              />
            </span>
            {copyNote && (
              <p role="status" className="w-full text-xs">
                {copyNote.text}{" "}
                <button type="button" className="underline underline-offset-2" disabled={restoreCopy.isPending} onClick={() => restoreCopy.mutate(copyNote)}>
                  Undo
                </button>
              </p>
            )}
            {undoNote && (
              <p role="status" className="w-full text-xs">
                {undoNote}
              </p>
            )}
            {selection.all && stream.total > SELECTION_AS_ONE && (
              <p role="status" className="w-full text-xs">
                {freeze.isLoading
                  ? `Preparing all ${fmt(stream.total)} messages to add as one selection`
                  : freeze.data
                    ? `All ${fmt(freeze.data.event_count)} messages (${fmt(freeze.data.record_count)} records, every copy included) will be added as one selection.`
                    : ""}
              </p>
            )}
          </div>
          {view.hl && view.thread && (
            <div className="flex flex-wrap items-center gap-2 border-b bg-status-review-soft px-3 py-1.5 text-xs">
              <p role="status">
                {matches.isLoading
                  ? "Showing the whole conversation. Counting the messages your search matched here."
                  : matches.data
                    ? `Showing the whole conversation. Your search matched ${fmt(matches.data.total)} ${matches.data.total === 1 ? "message" : "messages"} here.`
                    : "Showing the whole conversation. The matches could not be counted."}
              </p>
              {matches.data && matches.data.events.length > 1 && (
                <>
                  <Button size="sm" variant="outline" onClick={() => stepMatch(-1)}>
                    Previous match
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => stepMatch(1)}>
                    Next match
                  </Button>
                  <span>
                    Match {fmt(matchAt + 1)} of {fmt(matches.data.events.length)}
                  </span>
                </>
              )}
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => navigate(-1)}>
                Back to results
              </Button>
            </div>
          )}
          {streamFilter ? (
            <StreamList
              // A new thread, person or filter starts with nothing selected (review of 03-3: Select all carried over).
              key={JSON.stringify(streamFilter)}
              stream={stream}
              caseId={caseId}
              caseName={caseQ.data?.title ?? "This case"}
              filterWords={filterWords}
              zoneName={stream.index?.zone.name ?? zoneName}
              zone={stream.index?.zone.name ?? zoneName}
              zoneBasis={stream.index?.zone.basis}
              globalKeys
              jumpTo={jump}
              highlight={view.hl ? { query: view.hl, exact: view.hlExact } : null}
              onOpenRecord={(row) => setRecordUid(row.record_uid)}
              onFocusRow={setFocused}
              onSelectionChange={onSelectionChange}
              rowExtra={(row) => (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {usedIn[row.record_uid] && <span className="text-muted-foreground">{usedIn[row.record_uid]}</span>}
                  {row.copies.count > 1 && !view.everyCopy && (
                    <>
                      <span>Found {fmt(row.copies.count)} times</span>
                      <Button size="sm" variant="link" className="h-auto p-0 text-xs" onClick={() => setCopyRow(row)}>
                        Not a copy
                      </Button>
                    </>
                  )}
                </div>
              )}
            />
          ) : (
            <p className="p-4 text-sm text-muted-foreground">{threadsQ.isLoading ? "Loading the conversations" : view.tab === "threads" ? "No conversation matches these filters." : ""}</p>
          )}
          {strip.length > 0 && (
            <div role="group" aria-label="Message density">
              <TimeStrip days={strip} zone={stream.index?.zone.label ?? zoneName} onPickDay={(day) => setJump({ day, seq: Date.now() })} />
            </div>
          )}
        </section>
        {around && (
          <aside role="region" aria-label="Around this time" className="flex w-80 shrink-0 flex-col gap-2 overflow-auto border-l bg-card p-3 text-sm">
            <div className="flex items-baseline justify-between">
              <h2 className="font-semibold">Around this time</h2>
              <Button size="sm" variant="ghost" onClick={() => setAround(null)}>
                Close
              </Button>
            </div>
            <p className="text-xs">
              {AROUND_MINUTES} minutes either side of {around.time.row}
              {view.phones.length ? "" : ", on every phone"}.
            </p>
            {aroundQ.isLoading && <p className="text-xs">Loading</p>}
            {aroundQ.isError && <p role="alert">{failureText(aroundQ.error, "What happened around this time could not be loaded.")}</p>}
            {aroundQ.data && (
              <>
                <p className="text-xs font-medium">
                  {fmt(aroundQ.data.items.reduce((s, t) => s + t.event_count, 0))} messages in {fmt(aroundQ.data.items.length)} {aroundQ.data.items.length === 1 ? "thread" : "threads"}
                </p>
                <ul className="flex flex-col gap-1">
                  {aroundQ.data.items.map((t) => (
                    <li key={t.thread_key}>
                      <button type="button" className="w-full rounded px-1 py-0.5 text-left hover:bg-muted" onClick={() => (setView({ tab: "threads", thread: t.thread_key, people: [] }), setAround(null))}>
                        {t.title} on {t.phone.label}: {fmt(t.event_count)} {t.event_count === 1 ? "message" : "messages"}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
        )}
        <PhoneRecordPanel caseId={caseId} recordUid={recordUid} zone={stream.index?.zone.name} onClose={() => setRecordUid(null)} />
      </div>
      {streamFilter && exporting && <ExportDialog caseId={caseId} filter={streamFilter} words={filterWords} open={exporting} onOpenChange={setExporting} />}
      <Dialog open={!!copyRow} onOpenChange={(v) => !v && (setCopyRow(null), notCopy.reset())}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Not a copy</DialogTitle>
            <DialogDescription>
              This message was found {fmt(copyRow?.copies.count ?? 0)} times and is shown once. Say why it is a separate message. Your name, the time and the reason are kept, and it can be undone.
            </DialogDescription>
          </DialogHeader>
          <label className="flex flex-col gap-1 text-sm">
            Reason
            <textarea className="rounded border bg-background p-1" value={copyReason} onChange={(e) => setCopyReason(e.target.value)} />
          </label>
          {notCopy.isError && <p role="alert" className="text-sm">{failureText(notCopy.error, "The decision could not be saved.")}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCopyRow(null)}>
              Cancel
            </Button>
            <Button disabled={!copyReason.trim() || notCopy.isPending} onClick={() => notCopy.mutate()}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default ConversationsPage
