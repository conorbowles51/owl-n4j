import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api-client"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useCase } from "@/features/cases/hooks/use-cases"
import { installKeymap, register } from "@/lib/keymap"
import {
  failureText,
  freezeSelection,
  getSelection,
  getSavedView,
  saveView,
  getParticipants,
  getPhones,
  getThreads,
  markNotACopy,
  markReviewed,
  translateThread,
  undoReviewed,
  type ThreadSort,
  StaleSnapshotError,
  streamLocate,
  streamIndex,
} from "@/features/phones/api"
import { liveCollectClient, undoCollect, type CollectLink, type CollectResult, type CollectTarget } from "@/features/phones/collect.api"
import { MessageTranslation } from "@/features/phones/components/MessageTranslation"
import { AcrossBadges, AcrossBadgesSource } from "@/features/phones/AcrossBadges"
import { useAcrossBadges } from "@/features/phones/across-badges"
import { PhoneRecordPanel } from "@/features/phones/components/RecordPanel"
import { FindInResults } from "@/features/phones/components/FindInResults"
import { StreamList } from "@/features/phones/components/StreamList"
import { useCollectTargets, useUsedIn } from "@/features/phones/hooks/use-collect"
import { useStream } from "@/features/phones/hooks/use-stream"
import { ExportDialog } from "./ExportDialog"
import { phoneSettingsQuery, phoneThreadsQuery } from "@/features/phones/phone-queries"
import { SplitForReview } from "./SplitForReview"
import { ThreadReviewBar } from "./ThreadReviewBar"
import type { ReadRow } from "./use-reading-position"
import { ThreadAttachments } from "./ThreadAttachments"
import { PersonScope } from "./PersonScope"
import { ConversationFilters } from "./ConversationFilters"
import { useStreamDensity } from "@/features/phones/hooks/use-stream-density"
import { useMediaQuery } from "@/hooks/use-media-query"
import { useThreadMatches } from "./use-thread-matches"
import { dayZoneOf, filterChipWords, filterWordsOf, hasFilters, NO_FILTERS, viewFromSearch, viewToFilter, viewToSearch, type ConversationView } from "@/features/phones/lib/filter-url"
import { rememberSpot } from "@/features/phones/lib/continue-reading"
import { translateWords } from "@/features/phones/lib/translate-words"
import { labelText } from "@/features/phones/lib/labels"
import type { ReplyTarget, StreamRow, ThreadRow } from "@/features/phones/schemas"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { fmt } from "@/features/phones/ui/count-sentence"
import { ScopeBar, type Scope } from "@/features/phones/ui/ScopeBar"
import { SignificantNote } from "@/features/phones/ui/SignificantNote"
import { EMPTY_SCOPE, scopeWords } from "@/features/phones/ui/scope"
import { useChatStore } from "@/features/chat/stores/chat.store"
import { useUIStore } from "@/stores/ui.store"
import { TimeStrip, type StripDay } from "@/features/phones/ui/TimeStrip"
import { GoToDate } from "@/features/phones/components/GoToDate"
import { useNotebookStore } from "@/features/notebook/notebook.store"

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
  // Each change builds on the last one asked for, not on the last render: under load a second filter chosen before the
  // page has drawn the first would otherwise put the first back as it was.
  const latestView = useRef(view)
  useLayoutEffect(() => {
    latestView.current = view
  }, [view])
  const setView = useCallback(
    (patch: Partial<ConversationView> | ((v: ConversationView) => Partial<ConversationView>), replace = false) => {
      const next = { ...latestView.current, ...(typeof patch === "function" ? patch(latestView.current) : patch) }
      latestView.current = next
      navigate({ pathname: location.pathname, search: viewToSearch(next, fixedPhone) }, { replace })
    },
    [navigate, location.pathname, fixedPhone],
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
  const settingsQ = useQuery({ ...phoneSettingsQuery(caseId), enabled: !!caseId })
  const zoneName = settingsQ.data?.effective.name ?? "UTC"

  const listFilter = useMemo(() => viewToFilter(caseId, view, zoneName, false), [caseId, view, zoneName])
  const threadsQ = useQuery({
    ...phoneThreadsQuery(listFilter, view.threadSort),
    enabled: !!caseId && settingsQ.isSuccess,
  })
  const peopleQ = useQuery({
    queryKey: ["phone-people", listFilter],
    queryFn: () => getParticipants(listFilter),
    enabled: !!caseId && settingsQ.isSuccess && (view.tab === "people" || view.people.length > 0),
  })
  const threads = useMemo(() => threadsQ.data?.items ?? [], [threadsQ.data])
  const narrowed = hasFilters(view)

  // 07 section 4.3: below 1440 px the thread list collapses to a 48 px rail, and picking a thread collapses it again
  const wide = useMediaQuery("(min-width: 1440px)")
  const [railOpen, setRailOpen] = useState(false)
  const railed = !wide && !railOpen
  const { density, setDensity, saveFailed } = useStreamDensity()

  // D-38: the first thread opens on arrival, so j, r, m and c act at once (07 J-8b, J-12, J-13). A saved selection
  // opens whole: its frozen total and the list's total agree until a thread is picked.
  useEffect(() => {
    if (view.tab === "threads" && !view.thread && !view.record && !view.selection && threads.length) setView({ thread: threads[0].thread_key }, true)
  }, [view.tab, view.thread, view.record, view.selection, threads, setView])
  // A filter that leaves the open thread with no message moves to the first thread that has one; with none matching
  // the list says so. Only once the list of this filter has arrived, and never away from a thread opened with no filter.
  useEffect(() => {
    if (view.tab !== "threads" || !narrowed || !view.thread || !threadsQ.isSuccess || threadsQ.isPlaceholderData) return
    if (threads.some((t) => t.thread_key === view.thread)) return
    setView({ thread: threads[0]?.thread_key ?? null, at: null }, true)
  }, [view.tab, view.thread, narrowed, threads, threadsQ.isSuccess, threadsQ.isPlaceholderData, setView])

  // A link to one record (?record=) reads every message of the phones in scope with that record open beside it; a
  // saved selection (?selection=) reads its frozen records.
  const ready = view.tab === "threads" ? !!view.thread || !!view.record || !!view.selection : view.people.length > 0
  const streamFilter = useMemo(() => (ready && settingsQ.isSuccess ? viewToFilter(caseId, view, zoneName, true) : null), [ready, settingsQ.isSuccess, caseId, view, zoneName])
  const stream = useStream(streamFilter)
  // the toggle states what it hides (07 XF-11): the same view without it, counted by the same index
  const allRecords = useQuery({
    queryKey: ["phone-stream-all", streamFilter],
    queryFn: () => streamIndex({ ...streamFilter!, significant_only: false }),
    enabled: !!streamFilter && view.significant,
  })
  const allCount = allRecords.data?.counts.events
  const significantHidden = view.significant && stream.index && allCount !== undefined
    ? `${fmt(Math.max(0, allCount - stream.total))} of ${fmt(allCount)} messages and calls in this view are hidden.`
    : null

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
    if (current) rememberSpot(caseId, { thread: current.thread_key, extraction: current.phone.extraction_id, at: new Date().toISOString() })
  }, [caseId, current])

  // ---- record panel, focus, selection --------------------------------------------------------------------------
  const [recordUid, setRecordUid] = useState<string | null>(view.record)
  const [focused, setFocused] = useState<StreamRow | null>(null)
  const [selection, setSelection] = useState<{ rows: StreamRow[]; all: boolean }>({ rows: [], all: false })
  // Where the person is reading: the row they focused or, while scrolling, the top row. A ref, so reading never
  // re-renders the page; the bar reads it on its own beat (use-reading-position).
  const readRow = useRef<ReadRow | null>(null)
  const onReadRow = useCallback((row: StreamRow) => { readRow.current = { event_uid: row.event_uid, instant: row.time.instant ?? null } }, [])
  useEffect(() => { readRow.current = null }, [view.thread])
  const onFocusRead = useCallback((row: StreamRow | null) => { setFocused(row); if (row) onReadRow(row) }, [onReadRow])
  const onSelectionChange = useCallback((rows: StreamRow[], all: boolean) => setSelection({ rows, all }), [])
  const [exporting, setExporting] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [jump, setJump] = useState<{ day: string | null; seq: number; offset?: number } | null>(null)
  const [findHl, setFindHl] = useState<string | null>(null)
  const [goOpen, setGoOpen] = useState(false)
  const listRoot = useRef<HTMLDivElement>(null)

  // ---- a search hit: the whole thread, its matches marked, stepped through (03 S-8) -------------------------------
  const matches = useThreadMatches(view.hl && view.thread ? streamFilter : null, view.hl, view.hlExact)
  const [matchAt, setMatchAt] = useState(0)
  const goTo = useCallback(
    async (eventUid: string): Promise<boolean> => {
      if (!streamFilter || !stream.index) return false
      try {
        const loc = await streamLocate(streamFilter, stream.index.snapshot, eventUid)
        setJump({ day: loc.day, offset: loc.offset, seq: Date.now() })
        return true
      } catch {
        /* the message left the list (a stale snapshot re-reads it); the list stays where it is */
        return false
      }
    },
    [streamFilter, stream.index],
  )
  // A reply's original: in place when this list holds it, else in its own conversation with the filters cleared, and
  // the list says so. Back returns to the reply.
  const [originalNote, setOriginalNote] = useState<{ at: string | null; text: string } | null>(null)
  const goToOriginal = useCallback(
    async (target: ReplyTarget, row: StreamRow) => {
      setOriginalNote(null)
      if (streamFilter && stream.index) {
        try {
          const loc = await streamLocate(streamFilter, stream.index.snapshot, target.event_uid)
          setJump({ day: loc.day, offset: loc.offset, seq: Date.now() })
          return
        } catch (e) {
          // Only "not in this list" moves the reader; any other failure leaves the view and every filter as it is.
          if (e instanceof StaleSnapshotError) {
            stream.reload()
            setOriginalNote({ at: view.at, text: "The list changed while that was being found. It has been read again, so try once more." })
            return
          }
          if (!(e instanceof ApiError && e.status === 404)) {
            setOriginalNote({ at: view.at, text: failureText(e, "That message could not be found just now. Nothing was changed.") })
            return
          }
        }
      }
      const cleared = narrowed || view.significant
      setOriginalNote({ at: target.event_uid, text: `That message is not in this list, so it is shown in its own conversation${cleared ? " with the filters cleared" : ""}. Back returns you here.` })
      setView({ ...NO_FILTERS, significant: false, tab: "threads", people: [], record: null, selection: null, thread: target.thread_key ?? `none:${row.phone.extraction_id}`, at: target.event_uid })
    },
    [streamFilter, stream, narrowed, view.at, view.significant, setView],
  )
  const arrivedAt = useRef<string | null>(null)
  useEffect(() => {
    // open at the hit's message once the list is ready; going Back and to the same message again arrives again
    if (!view.at) arrivedAt.current = null
    if (!view.at || !streamFilter || !stream.index || arrivedAt.current === view.at) return
    const at = view.at
    // Right after a change of thread the index is still the last filter's and the server refuses it: this runs again
    // when the new index arrives, so only an answered ask counts as arrived.
    void goTo(at).then((ok) => {
      if (ok) arrivedAt.current = at
    })
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
  // the first 400 rows' marks, asked for once those rows have all arrived (a list arrives in many windows)
  const marked = useMemo(() => {
    const out: string[] = []
    let complete = stream.status === "ready"
    for (let i = 0, rowsSeen = 0; i < stream.count && rowsSeen < 400; i++) {
      const it = stream.item(i)
      if (it.type !== "row") continue
      rowsSeen++
      if (it.row) out.push(it.row.record_uid)
      else if (it.state === "loading") complete = false
    }
    return { ids: out, complete }
  }, [stream])
  const { usedIn, refresh: refreshUsedIn } = useUsedIn(caseId, marked.ids, marked.complete)
  const across = useAcrossBadges(caseId, stream)
  const chipWords = filterChipWords(view)
  const narrowWords = filterWordsOf(view)
  const filterWords = `${current ? `${current.title} on ${current.phone.label}` : view.people.length ? "Messages with the chosen people" : "Conversations"}${view.significant ? ", significant phone identities only" : ""}${narrowWords ? `, ${narrowWords}` : ""}`
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
  // XF-10: the chat gets the open thread, the scope words and the selected record ids, never the messages' text
  const askAboutThese = () => {
    const ids: string[] = []
    for (const r of selection.rows) if (!ids.includes(r.record_uid)) ids.push(r.record_uid)
    useChatStore.getState().setPhoneContext({
      caseId, thread: view.thread, thread_title: current?.title ?? null, scope_words: chipWords ? `${scopeWords(scope)}, ${chipWords}` : scopeWords(scope),
      scope_total: stream.status === "ready" ? stream.total : null, record_ids: ids,
      // "select all" covers every message in scope, but only the rows loaded on screen have ids to send
      selected_total: selection.all && stream.status === "ready" ? stream.total : ids.length,
    })
    useUIStore.getState().expandGraphPanelTo("chat")
  }
  // CO-6: a note about the selected messages opens in the Notebook with them linked and pinned beside the composer
  const writeNote = () => {
    const ids: string[] = []
    for (const r of selection.rows) if (!ids.includes(r.record_uid)) ids.push(r.record_uid)
    const selected = selection.all && stream.status === "ready" ? stream.total : selection.rows.length
    const linked = links.length === 1 && links[0].target_type === "phone_selection" ? (freeze.data?.event_count ?? 0) : selection.rows.length
    useNotebookStore.getState().startDraft(
      links.map((l) => ({ target_type: l.target_type, target_id: l.target_id, target_label: l.label ?? null })),
      { caseId, selected, linked, recordIds: ids },
    )
    useUIStore.getState().expandGraphPanelTo("notebook")
  }
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
  // 05 17.5: every message with text in this conversation is translated on the server, one translation each
  const [translateNote, setTranslateNote] = useState<{ thread: string; text: string } | null>(null)
  // ---- Save this view (07 section 6): the filter kept in a Workspace note; a saved view opens re-run live ---------
  const savedViewId = new URLSearchParams(location.search).get("saved_view")
  const savedView = useQuery({
    queryKey: ["phone-view", caseId, savedViewId],
    queryFn: () => getSavedView(caseId, savedViewId!),
    enabled: !!caseId && !!savedViewId,
    retry: false,
  })
  const saveThisView = useMutation({
    mutationFn: () => saveView(streamFilter!, `${location.pathname}?${viewToSearch({ ...view, at: null, record: null }, fixedPhone)}`, filterWords),
  })

  const translate = useMutation({
    mutationFn: (thread: string) => translateThread(caseId, thread),
    onSuccess: (c, thread) => {
      setTranslateNote({ thread, text: translateWords(c) })
      void qc.invalidateQueries({ queryKey: ["phone-translation", caseId] })
    },
    onError: (e, thread) => setTranslateNote({ thread, text: failureText(e, e instanceof Error && e.message ? e.message : "The translation could not be asked for.") }),
  })
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
      { key: "g", label: "Go to date", run: () => setGoOpen(true) },
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
        {savedViewId && (
          <p role="status" className="w-full text-sm" data-testid="saved-view">
            {savedView.isLoading && "Opening the saved view"}
            {savedView.isError && failureText(savedView.error, "This saved view could not be opened.")}
            {savedView.data && `${savedView.data.sentence} The list below is the view re-run now.`}{" "}
            {savedView.data?.replaced && <span className="text-status-review">{savedView.data.replaced}.</span>}
          </p>
        )}
        {!view.noTime && (
          // opened from a crossing that names days (07 XF-1, XF-4): records with no time cannot be placed on a day
          <p role="status" className="w-full text-sm" data-testid="dated-only">
            Showing only messages and calls with a time.{" "}
            <button type="button" className="underline underline-offset-2" onClick={() => setView({ noTime: true })}>
              Include those with no time
            </button>
          </p>
        )}
        {counts && (
          <p className="text-sm" data-testid="not-reviewed">
            Not yet reviewed: {fmt(counts.not_reviewed ?? 0)} of {fmt(counts.threads ?? 0)} threads
          </p>
        )}
        {counts && (
          <Button size="sm" variant="outline" onClick={() => setSplitting(true)}>
            Split for review…
          </Button>
        )}
        <SplitForReview caseId={caseId} filter={listFilter} scopeWords={chipWords ? `${scopeWords(scope)}, ${chipWords}` : scopeWords(scope)} open={splitting} onClose={() => setSplitting(false)} />
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
        {railed && (
          <nav aria-label="Threads and people" className="flex w-12 shrink-0 flex-col border-r bg-card" data-testid="thread-rail">
            <button type="button" className="flex-1 py-2 text-sm font-medium [writing-mode:vertical-rl] hover:bg-muted" aria-expanded={false} onClick={() => setRailOpen(true)}>
              {view.tab === "threads" ? `Threads (${fmt(threadsQ.data?.counts.threads ?? threads.length)})` : `People (${fmt(peopleQ.data?.items.length ?? 0)})`}
            </button>
          </nav>
        )}
        {!railed && <nav aria-label="Threads and people" className="flex w-80 shrink-0 flex-col border-r bg-card">
          <div className="flex gap-1 border-b p-2" role="group" aria-label="List">
            <Button size="sm" variant={view.tab === "threads" ? "secondary" : "ghost"} aria-pressed={view.tab === "threads"} onClick={() => setView({ tab: "threads", people: [] })}>
              Threads
            </Button>
            <Button size="sm" variant={view.tab === "people" ? "secondary" : "ghost"} aria-pressed={view.tab === "people"} onClick={() => setView({ tab: "people", thread: null })}>
              People
            </Button>
            {!wide && (
              <Button size="sm" variant="ghost" className="ml-auto" aria-label="Collapse the list" onClick={() => setRailOpen(false)}>
                Collapse
              </Button>
            )}
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
                  <p className="text-xs" data-testid="thread-count">
                    {narrowed && threadsQ.data.counts.threads_total !== undefined && shownThreads.length === threads.length ? `${fmt(threads.length)} of ${fmt(threadsQ.data.counts.threads_total)} threads have messages matching these filters` : shownThreads.length < threads.length ? `Showing ${fmt(shownThreads.length)} of ${fmt(threads.length)} threads` : `${fmt(threads.length)} threads`}
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
                      onClick={() => { setRailOpen(false); setView({ thread: t.thread_key, record: null }) }}
                      onKeyDown={(e) => { if (e.key === "Enter") { setRailOpen(false); setView({ thread: t.thread_key, record: null }) } }}
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
        </nav>}
        <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col" ref={listRoot}>
          <ScopeBar scope={scope} onChange={onScope} narrowed={narrowed} count={stream.status === "ready" && stream.index ? { shown: stream.total, total: stream.total, noun: "messages" } : null}>
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
            <SignificantNote caseId={caseId} on={view.significant} onChange={(on) => setView({ significant: on })} hiddenWords={significantHidden} />
            <ConversationFilters view={view} setView={setView} listFilter={listFilter} zoneWords={dayZoneOf(view, zoneName)} threadCounts={threadsQ.data?.counts}
              phones={fixedPhone ? undefined : phones.map((p) => ({ id: p.extraction_id, label: p.label }))} />
          </ScopeBar>
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-1.5 text-sm">
            {current ? (
              <span className="font-medium">
                {current.title} on {current.phone.label}
                {current.app ? `, ${current.app}` : ""}
              </span>
            ) : null}
            {current && (
              <ThreadAttachments caseId={caseId} extraction={current.phone.extraction_id} threadKey={current.thread_key} title={current.title}
                back={`${location.pathname}?${viewToSearch({ ...view, at: focused?.event_uid ?? view.at }, fixedPhone)}`} />
            )}
            {(view.deleted === true || !!view.oneDeletion) && (
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
              <label className="inline-flex items-center gap-1 text-xs">
                Density
                <select className="rounded border bg-card px-1 py-0.5" value={density} onChange={(e) => setDensity(e.target.value as "comfortable" | "compact")}>
                  <option value="comfortable">Comfortable</option>
                  <option value="compact">Compact</option>
                </select>
              </label>
              {saveFailed && <span role="alert" className="text-xs">The density could not be saved.</span>}
              <Button size="sm" variant="outline" disabled={!streamFilter} onClick={() => setExporting(true)}>
                Export…
              </Button>
              {view.thread && (
                <Button size="sm" variant="outline" disabled={translate.isPending} onClick={() => translate.mutate(view.thread!)}>
                  Translate this conversation
                </Button>
              )}
              {view.thread && (
                <Button size="sm" variant="outline" disabled={review.isPending} onClick={() => review.mutate({ thread: view.thread!, undo: false })}>
                  Mark reviewed <kbd className="ml-1 text-xs text-muted-foreground">m</kbd>
                </Button>
              )}
              <Button size="sm" variant="outline" disabled={!focused?.time.instant} onClick={() => focused && setAround(focused)}>
                Around this time <kbd className="ml-1 text-xs text-muted-foreground">a</kbd>
              </Button>
              {focused?.time.instant && (
                <Button size="sm" variant="outline" asChild>
                  <Link to={`/cases/${encodeURIComponent(caseId)}/phone-analyses/incident-window?${new URLSearchParams({ at: focused.time.instant, label: "the selected message or call" }).toString()}`}>
                    Open the window around this
                  </Link>
                </Button>
              )}
              <Button size="sm" variant="outline" disabled={!streamFilter || selection.rows.length === 0} onClick={askAboutThese}
                title={selection.rows.length === 0 ? "Select messages to ask about them" : undefined}>
                {selection.rows.length === 0 ? "Select messages to ask about them" : "Ask about these messages"}
              </Button>
              {stream.index && (
                <GoToDate days={stream.index.items} where={view.thread && !view.people.length ? "in this thread" : "in these results"} open={goOpen} onOpenChange={setGoOpen}
                  onGo={(day) => { setGoOpen(false); setJump({ day, seq: Date.now() }) }} />
              )}
              <Button size="sm" variant="outline" disabled={links.length === 0} onClick={writeNote}
                title={selection.rows.length === 0 ? "Select messages to write a note about them" : undefined}>
                Write a note about these
              </Button>
              {streamFilter && (
                <Button size="sm" variant="outline" disabled={saveThisView.isPending} onClick={() => saveThisView.mutate()}>
                  Save this view
                </Button>
              )}
              {saveThisView.data && (
                <span role="status" className="text-xs">
                  Saved as a Workspace note ({fmt(saveThisView.data.event_count)} {saveThisView.data.event_count === 1 ? "message" : "messages"} now).{" "}
                  <Link className="underline underline-offset-2" to={`/cases/${encodeURIComponent(caseId)}/workspace?view=casework&entry=${encodeURIComponent(saveThisView.data.entry_id)}`}>
                    Open the note
                  </Link>
                </span>
              )}
              {saveThisView.isError && <span role="alert" className="text-xs">{failureText(saveThisView.error, "The view could not be saved.")}</span>}
              {streamFilter && (
                <FindInResults filter={streamFilter} snapshot={stream.index?.snapshot} onQuery={setFindHl}
                  onGo={(m) => setJump({ day: m.day, offset: m.offset, seq: Date.now() })} />
              )}
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
            {originalNote && originalNote.at === view.at && (
              <p role="status" className="w-full text-xs" data-testid="original-note">
                {originalNote.text}
              </p>
            )}
            {translateNote && translateNote.thread === view.thread && (
              <p role="status" className="w-full text-xs" data-testid="translate-note">
                {translateNote.text}
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
          {view.thread && <ThreadReviewBar caseId={caseId} threadKey={view.thread} extraction={current?.phone.extraction_id ?? null} readRow={readRow} onResume={(uid) => void goTo(uid)} />}
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
          {streamFilter && <AcrossBadgesSource run={across.run} />}
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
              highlight={findHl ? { query: findHl, exact: false } : view.hl ? { query: view.hl, exact: view.hlExact } : null}
              onOpenRecord={(row) => setRecordUid(row.record_uid)}
              onFocusRow={onFocusRead}
              onTopRow={onReadRow}
              onSelectionChange={onSelectionChange}
              density={density}
              onGoToOriginal={(target, row) => void goToOriginal(target, row)}
              rowExtra={(row) => (
                <>
                <MessageTranslation caseId={caseId} row={row} />
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {usedIn[row.record_uid] && <span className="text-muted-foreground">{usedIn[row.record_uid]}</span>}
                  <AcrossBadges caseId={caseId} badges={across.forRow(row)} />
                  {row.copies.count > 1 && !view.everyCopy && (
                    <>
                      <span>Found {fmt(row.copies.count)} times</span>
                      <Button size="sm" variant="link" className="h-auto p-0 text-xs" onClick={() => setCopyRow(row)}>
                        Not a copy
                      </Button>
                    </>
                  )}
                </div>
                </>
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
