import { useCallback, useEffect, useMemo, useState } from "react"
import { Activity, BookOpen, Loader2, SlidersHorizontal } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

import {
  useCommsEntities,
  useCommsEnvelope,
  useCommsSourceApps,
  useCommsThreads,
  useMessageSearch,
  useThreadDetail,
} from "../../hooks/use-cellebrite"
import type { CellebriteRecord, CommsItem, CommsThread, CommsType, PhoneReport, RailSelection } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import type { CommsSeed } from "../shared/cellebrite-types"
import { CommsParticipantsFilter } from "./CommsParticipantsFilter"
import { CommsThreadList } from "./CommsThreadList"
import { CommsThreadView } from "./CommsThreadView"
import { CommsTimelineFlyover } from "./CommsTimelineFlyover"
import { CommsToolbar } from "./CommsToolbar"
import {
  ALL_COMMS_TYPES,
  applyEntityNames,
  dedupeThreads,
  itemId,
  itemKind,
  mergeSeedParticipants,
  messageTitle,
  participantSummary,
  reportLabelMap,
  sourceAppLabel,
  threadKey,
  threadTypesForTypes,
  typeArray,
  type CommsParticipantMode,
  type CommsViewMode,
  type ParticipantFilter,
} from "./commsUtils"

const DEFAULT_THREAD_DETAIL_LIMIT = 500
const MAX_THREAD_DETAIL_LIMIT = 500000

export function CommsTab({
  active,
  caseId,
  reportKeys,
  reports,
  query,
  dateFilters,
  seed,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  reports: PhoneReport[]
  query: string
  dateFilters: { startDate: string; endDate: string }
  seed: CommsSeed | null
  onSelect: (selection: RailSelection) => void
}) {
  const [participants, setParticipants] = useState<ParticipantFilter[]>(() =>
    seed ? mergeSeedParticipants([], seed.participantKeys) : []
  )
  const [participantsMode, setParticipantsMode] = useStoredMode<CommsParticipantMode>(
    `cb.comms.participantsMode.${caseId}`,
    seed?.participantKeys.length ? "any" : "split"
  )
  const [activeTypes, setActiveTypes] = useState<Set<CommsType>>(() =>
    seed?.type && seed.type !== "all" ? new Set([seed.type]) : new Set(ALL_COMMS_TYPES)
  )
  const [activeApps, setActiveApps] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState(query)
  const [windowStart, setWindowStart] = useState("")
  const [windowEnd, setWindowEnd] = useState("")
  const [viewMode, setViewMode] = useStoredMode<CommsViewMode>(`cb.comms.viewMode.${caseId}`, "browse")
  const [timelineOpen, setTimelineOpen] = useStoredBoolean(`cb.comms.timelineFlyover.${caseId}`, false)
  const [selectedThreadKey, setSelectedThreadKey] = useState<string | null>(null)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [threadItemLimit, setThreadItemLimit] = useState(DEFAULT_THREAD_DETAIL_LIMIT)
  const seedId = seed?.id
  const seedKeys = useMemo(() => seed?.participantKeys ?? [], [seed?.participantKeys])
  const seedType = seed?.type ?? "all"

  useEffect(() => {
    setSearch(query)
  }, [query])

  useEffect(() => {
    if (!seedId) return
    if (seedKeys.length > 0) {
      setParticipantsMode("any")
      setParticipants((current) => mergeSeedParticipants(current, seedKeys))
    }
    setActiveTypes(seedType !== "all" ? new Set([seedType]) : new Set(ALL_COMMS_TYPES))
    setSelectedThreadKey(null)
  }, [seedId, seedKeys, seedType, setParticipantsMode])

  const entitiesQuery = useCommsEntities(caseId, reportKeys, active, true)
  const sourceAppsQuery = useCommsSourceApps(caseId, reportKeys, active)
  const entities = useMemo(
    () => (entitiesQuery.data?.entities ?? []) as CellebriteRecord[],
    [entitiesQuery.data?.entities]
  )
  const sourceApps = useMemo(() => sourceAppsQuery.data?.apps ?? [], [sourceAppsQuery.data?.apps])

  useEffect(() => {
    setParticipants((current) => applyEntityNames(current, entities))
  }, [entities])

  useEffect(() => {
    if (!sourceApps.length) return
    setActiveApps((current) => {
      if (current.size === 0) return current
      const available = new Set(sourceApps.map(sourceAppLabel))
      const next = new Set([...current].filter((app) => available.has(app)))
      return next.size === current.size ? current : next
    })
  }, [sourceApps])

  const participantFilters = useMemo(() => {
    const fromKeys: string[] = []
    const toKeys: string[] = []
    const anyKeys: string[] = []
    participants.forEach((participant) => {
      if (participantsMode === "any") {
        anyKeys.push(participant.key)
      } else if (participant.role === "any") {
        fromKeys.push(participant.key)
        toKeys.push(participant.key)
      } else if (participant.role === "from") {
        fromKeys.push(participant.key)
      } else if (participant.role === "to") {
        toKeys.push(participant.key)
      }
    })
    return {
      fromKeys: fromKeys.length ? fromKeys : null,
      toKeys: toKeys.length ? toKeys : null,
      participantKeys: anyKeys.length ? anyKeys : null,
    }
  }, [participants, participantsMode])

  const startDate = windowStart || dateFilters.startDate
  const endDate = windowEnd || dateFilters.endDate
  const sourceAppFilter = activeApps.size ? [...activeApps] : null

  const threadsQuery = useCommsThreads(
    caseId,
    {
      reportKeys,
      ...participantFilters,
      sourceApps: sourceAppFilter,
      threadTypes: threadTypesForTypes(activeTypes),
      startDate: startDate || null,
      endDate: endDate || null,
      limit: 900,
    },
    active
  )
  const envelopeQuery = useCommsEnvelope(
    caseId,
    {
      reportKeys,
      ...participantFilters,
      sourceApps: sourceAppFilter,
      types: typeArray(activeTypes),
      startDate: startDate || null,
      endDate: endDate || null,
    },
    active
  )
  const deepSearchQuery = useMessageSearch(
    caseId,
    { q: search, reportKeys, limit: 300 },
    active && search.trim().length > 1
  )

  const rawThreads = useMemo(() => threadsQuery.data?.threads ?? [], [threadsQuery.data?.threads])
  const threads = useMemo(() => dedupeThreads(rawThreads), [rawThreads])
  const deepThreadIds = useMemo(
    () => new Set(deepSearchQuery.data?.thread_ids ?? []),
    [deepSearchQuery.data?.thread_ids]
  )
  const filteredThreads = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return threads
    return threads.filter((thread) => {
      if (deepThreadIds.has(thread.thread_id)) return true
      const summary = participantSummary(thread)
      return [
        summary.title,
        thread.name,
        thread.thread_id,
        thread.thread_type,
        sourceAppLabel(thread),
        thread.participants?.map((participant) => `${participant.name ?? ""} ${participant.key ?? ""}`).join(" "),
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    })
  }, [deepThreadIds, search, threads])

  useEffect(() => {
    if (!active) return
    const selectedStillVisible =
      selectedThreadKey && filteredThreads.some((thread) => threadKey(thread) === selectedThreadKey)
    if (selectedStillVisible) return
    setSelectedThreadKey(filteredThreads[0] ? threadKey(filteredThreads[0]) : null)
  }, [active, filteredThreads, selectedThreadKey])

  const selectedThread = useMemo(
    () => filteredThreads.find((thread) => threadKey(thread) === selectedThreadKey) ?? null,
    [filteredThreads, selectedThreadKey]
  )

  const firstSearchMatch = useMemo(() => {
    if (!selectedThread) return null
    return (deepSearchQuery.data?.matches ?? []).find((match) => match.thread_id === selectedThread.thread_id) ?? null
  }, [deepSearchQuery.data?.matches, selectedThread])
  const firstSearchMatchId = firstSearchMatch ? itemId(firstSearchMatch, "") : null

  useEffect(() => {
    setThreadItemLimit(DEFAULT_THREAD_DETAIL_LIMIT)
  }, [firstSearchMatchId, selectedThreadKey])

  const threadDetailQuery = useThreadDetail(
    caseId,
    selectedThread,
    {
      limit: threadItemLimit,
      anchorKey: threadItemLimit === DEFAULT_THREAD_DETAIL_LIMIT ? firstSearchMatchId : null,
    },
    active && !!selectedThread
  )
  const loadedThreadItemCount =
    (threadDetailQuery.data?.items ?? threadDetailQuery.data?.messages ?? []).length
  const totalThreadItemCount =
    typeof threadDetailQuery.data?.total === "number"
      ? threadDetailQuery.data.total
      : Number(selectedThread?.item_count ?? selectedThread?.message_count ?? loadedThreadItemCount)
  const loadAllThreadItems = useCallback(() => {
    const nextLimit = Math.max(
      DEFAULT_THREAD_DETAIL_LIMIT,
      Math.min(MAX_THREAD_DETAIL_LIMIT, totalThreadItemCount)
    )
    setThreadItemLimit(nextLimit)
  }, [totalThreadItemCount])

  const reportsByKey = useMemo(() => reportLabelMap(reports), [reports])

  function selectThread(thread: CommsThread) {
    setSelectedThreadKey(threadKey(thread))
    setSelectedItemId(null)
  }

  function selectItem(item: CommsItem) {
    const id = itemId(item, "message")
    setSelectedItemId(id)
    onSelect({
      id,
      kind: itemKind(item) === "message" ? "message" : "event",
      title: messageTitle(item),
      payload: item,
    })
  }

  const modeBar = (
    <ModeBar
      viewMode={viewMode}
      timelineOpen={timelineOpen}
      onViewModeChange={setViewMode}
      onTimelineOpenChange={setTimelineOpen}
    />
  )

  const threadBody = (
    <div className="grid min-h-0 flex-1 grid-cols-[320px_minmax(0,1fr)] overflow-hidden">
      <aside className="flex min-h-0 flex-col overflow-hidden border-r border-border bg-card">
        <PaneHeader
          title="Threads"
          count={filteredThreads.length}
          loading={threadsQuery.isLoading || deepSearchQuery.isLoading}
        />
        <div className="min-h-0 flex-1">
          <CommsThreadList
            threads={filteredThreads}
            loading={threadsQuery.isLoading || entitiesQuery.isLoading}
            selectedThreadKey={selectedThreadKey}
            reportsByKey={reportsByKey}
            onSelect={selectThread}
          />
        </div>
      </aside>
      <main className="flex min-h-0 min-w-0 overflow-hidden">
        <CommsThreadView
          key={`${selectedThreadKey ?? "none"}:${firstSearchMatch ? search : ""}`}
          caseId={caseId}
          thread={selectedThread}
          detail={threadDetailQuery.data}
          loading={threadDetailQuery.isLoading}
          selectedItemId={selectedItemId}
          reportsByKey={reportsByKey}
          externalSearch={firstSearchMatch ? search : ""}
          onLoadAllItems={totalThreadItemCount > loadedThreadItemCount ? loadAllThreadItems : undefined}
          onItemSelect={selectItem}
        />
      </main>
    </div>
  )

  if (viewMode === "read") {
    return (
      <section className="relative flex h-full min-h-0 flex-col overflow-hidden">
        <div className="flex min-h-10 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
          {modeBar}
          <div className="ml-auto text-[11px] text-muted-foreground">
            Filter controls hidden, current filters still applied.
          </div>
        </div>
        {threadBody}
        {timelineOpen && (
          <CommsTimelineFlyover
            caseId={caseId}
            reportKeys={reportKeys}
            fromKeys={participantFilters.fromKeys}
            toKeys={participantFilters.toKeys}
            participantKeys={participantFilters.participantKeys}
            activeTypes={activeTypes}
            activeApps={activeApps}
            startDate={startDate}
            endDate={endDate}
            onClose={() => setTimelineOpen(false)}
            onItemSelect={selectItem}
          />
        )}
      </section>
    )
  }

  return (
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex min-h-10 shrink-0 items-center gap-2 border-b border-border bg-muted/20 px-3">
        {modeBar}
        <span className="text-[11px] text-muted-foreground">
          Browse mode: refine participants, apps, types, and time.
        </span>
        <Badge variant="slate" className="ml-auto">
          {compactNumber(envelopeQuery.data?.total)} records
        </Badge>
      </div>
      <CommsParticipantsFilter
        entities={entities}
        participants={participants}
        mode={participantsMode}
        loading={entitiesQuery.isLoading}
        onParticipantsChange={setParticipants}
        onModeChange={setParticipantsMode}
      />
      <CommsToolbar
        search={search}
        onSearchChange={setSearch}
        threadsShown={filteredThreads.length}
        threadsTotal={threads.length}
        activeTypes={activeTypes}
        onTypesChange={setActiveTypes}
        sourceApps={sourceApps}
        activeApps={activeApps}
        onAppsChange={setActiveApps}
        envelope={envelopeQuery.data ?? null}
        envelopeLoading={envelopeQuery.isLoading}
        startDate={startDate}
        endDate={endDate}
        onWindowChange={(nextStart, nextEnd) => {
          setWindowStart(nextStart)
          setWindowEnd(nextEnd)
        }}
      />
      {threadBody}
      {timelineOpen && (
        <CommsTimelineFlyover
          caseId={caseId}
          reportKeys={reportKeys}
          fromKeys={participantFilters.fromKeys}
          toKeys={participantFilters.toKeys}
          participantKeys={participantFilters.participantKeys}
          activeTypes={activeTypes}
          activeApps={activeApps}
          startDate={startDate}
          endDate={endDate}
          onClose={() => setTimelineOpen(false)}
          onItemSelect={selectItem}
        />
      )}
    </section>
  )
}

function PaneHeader({
  title,
  count,
  loading,
}: {
  title: string
  count: number
  loading?: boolean
}) {
  return (
    <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
      <span className="text-xs font-semibold">{title}</span>
      {loading && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
      <Badge variant="slate" className="ml-auto">{compactNumber(count)}</Badge>
    </div>
  )
}

function ModeBar({
  viewMode,
  timelineOpen,
  onViewModeChange,
  onTimelineOpenChange,
}: {
  viewMode: CommsViewMode
  timelineOpen: boolean
  onViewModeChange: (mode: CommsViewMode) => void
  onTimelineOpenChange: (open: boolean) => void
}) {
  const isRead = viewMode === "read"
  return (
    <div className="inline-flex items-center gap-1.5">
      <div className="inline-flex overflow-hidden rounded-md border border-border text-xs">
        <button
          type="button"
          onClick={() => onViewModeChange("browse")}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 px-2 transition-colors",
            !isRead ? "bg-secondary text-secondary-foreground" : "bg-card text-muted-foreground hover:bg-muted"
          )}
        >
          <SlidersHorizontal className="size-3.5" />
          Browse
        </button>
        <button
          type="button"
          onClick={() => onViewModeChange("read")}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 border-l border-border px-2 transition-colors",
            isRead ? "bg-secondary text-secondary-foreground" : "bg-card text-muted-foreground hover:bg-muted"
          )}
        >
          <BookOpen className="size-3.5" />
          Read
        </button>
      </div>
      <Button
        type="button"
        variant={timelineOpen ? "secondary" : "outline"}
        size="sm"
        className="h-7 gap-1.5 text-xs"
        onClick={() => onTimelineOpenChange(!timelineOpen)}
      >
        <Activity className="size-3.5" />
        Timeline
      </Button>
    </div>
  )
}

function useStoredMode<T extends string>(key: string, fallback: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return fallback
    const stored = window.localStorage.getItem(key)
    return (stored as T | null) ?? fallback
  })
  const update = useCallback((next: T) => {
    setValue(next)
    if (typeof window !== "undefined") window.localStorage.setItem(key, next)
  }, [key])
  return [value, update]
}

function useStoredBoolean(key: string, fallback: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    if (typeof window === "undefined") return fallback
    const stored = window.localStorage.getItem(key)
    return stored == null ? fallback : stored === "1"
  })
  const update = useCallback((next: boolean) => {
    setValue(next)
    if (typeof window !== "undefined") window.localStorage.setItem(key, next ? "1" : "0")
  }, [key])
  return [value, update]
}
