import { useMemo, useState, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import {
  Activity,
  CheckCircle2,
  Clock,
  Filter,
  FolderTree,
  GitBranch,
  Loader2,
  MapPin,
  MessageSquare,
  Network,
  Pencil,
  Play,
  RefreshCw,
  Search,
  Smartphone,
  Trash2,
  UserRound,
  Users,
  X,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"
import {
  useCellebriteCommunicationNetwork,
  useCellebriteCrossPhoneGraph,
  useCellebriteFiles,
  useCellebriteFilesTree,
  useCellebriteReports,
  useCellebriteTimeline,
  useCommsEnvelope,
  useCommsSourceApps,
  useCommsThreads,
  useDeleteCellebriteReport,
  useEventDetail,
  useEventRelated,
  useEventTracks,
  useEventTypes,
  useEvents,
  useLocationTiles,
  useMessageSearch,
  usePatchCellebriteReport,
  useRunIntersections,
  useThreadDetail,
} from "../hooks/use-cellebrite"
import type {
  CellebriteRecord,
  CellebriteTabKey,
  CommsItem,
  EventTypeCount,
  FileTreeNode,
  GraphLink,
  GraphNode,
  PhoneReport,
  RailSelection,
  TimelineItem,
} from "../types"
import { OverviewTab } from "./overview/OverviewTab"
import { UnifiedContactsTab } from "./unified/UnifiedContactsTab"
import { UnifiedContactDetail } from "./unified/UnifiedContactDetail"
import { SmallEmpty } from "./shared/SmallEmpty"
import {
  compactDate,
  compactNumber,
  isRecord,
  itemKey,
  readList,
  readNumber,
  readText,
  reportKey,
  reportTitle,
  selectedReportParams,
  truncate,
} from "./shared/cellebrite-format"
import type { CommsSeed } from "./shared/cellebrite-types"

type TabDef = {
  key: CellebriteTabKey
  label: string
  icon: typeof Smartphone
}

type DateFilters = {
  startDate: string
  endDate: string
}

type Column = {
  id: string
  label: string
  className?: string
  get: (row: CellebriteRecord) => ReactNode
}

const TABS: TabDef[] = [
  { key: "overview", label: "Overview", icon: Smartphone },
  { key: "unified", label: "Unified Contacts", icon: UserRound },
  { key: "comms", label: "Comms", icon: MessageSquare },
  { key: "events", label: "Events & Locations", icon: MapPin },
  { key: "timeline", label: "Timeline", icon: Clock },
  { key: "files", label: "Files", icon: FolderTree },
  { key: "graph", label: "Graph & Intersections", icon: Network },
]

const INTERSECTION_METHODS = ["spatial", "cell_tower", "wifi", "comm_hub", "convoy"]

export function CellebritePage() {
  const { id: caseId } = useParams()
  const [activeTab, setActiveTab] = useState<CellebriteTabKey>("overview")
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [query, setQuery] = useState("")
  const [dateFilters, setDateFilters] = useState<DateFilters>({
    startDate: "",
    endDate: "",
  })
  const [selection, setSelection] = useState<RailSelection | null>(null)
  const [commsSeed, setCommsSeed] = useState<CommsSeed | null>(null)

  const reportsQuery = useCellebriteReports(caseId)
  const reports = useMemo(() => reportsQuery.data?.reports ?? [], [reportsQuery.data?.reports])
  const allReportKeys = useMemo(() => reports.map(reportKey).filter(Boolean), [reports])
  const activeReportKeys = useMemo(() => {
    const kept = selectedKeys.filter((key) => allReportKeys.includes(key))
    return kept.length > 0 ? kept : allReportKeys
  }, [allReportKeys, selectedKeys])

  const selectedReports = useMemo(
    () => reports.filter((report) => activeReportKeys.includes(reportKey(report))),
    [activeReportKeys, reports]
  )
  const reportKeys = selectedReportParams(activeReportKeys)

  if (!caseId) {
    return (
      <EmptyState
        icon={Smartphone}
        title="No case selected"
        description="Open a case to inspect phone extractions."
      />
    )
  }

  if (reportsQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <header className="flex shrink-0 flex-col border-b border-border bg-card">
        <div className="flex min-h-14 items-center gap-3 px-4">
          <div className="flex size-9 items-center justify-center rounded-md border border-border bg-muted">
            <Smartphone className="size-5 text-amber-500" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold text-foreground">Cellebrite Phone Viewer</h1>
              <Badge variant={reports.length ? "success" : "slate"}>
                {reports.length} report{reports.length === 1 ? "" : "s"}
              </Badge>
            </div>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {selectedReports.length
                ? selectedReports.map(reportTitle).join(" / ")
                : "No reports selected"}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => reportsQuery.refetch()}>
              <RefreshCw className="size-3.5" />
              Refresh
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-2">
          <div className="flex min-w-72 flex-1 items-center gap-2">
            <Search className="size-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search names, messages, files, locations"
              className="h-8"
            />
          </div>
          <DateInput
            label="Start"
            value={dateFilters.startDate}
            onChange={(startDate) => setDateFilters((current) => ({ ...current, startDate }))}
          />
          <DateInput
            label="End"
            value={dateFilters.endDate}
            onChange={(endDate) => setDateFilters((current) => ({ ...current, endDate }))}
          />
          {(query || dateFilters.startDate || dateFilters.endDate) && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => {
                setQuery("")
                setDateFilters({ startDate: "", endDate: "" })
              }}
            >
              <X className="size-4" />
            </Button>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-t border-border px-3">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              className={cn(
                "flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-xs font-semibold transition-colors",
                activeTab === key
                  ? "border-amber-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
        </div>
      </header>

      {reports.length === 0 ? (
        <div className="flex flex-1 items-center justify-center overflow-hidden">
          <EmptyState
            icon={Smartphone}
            title="No phone reports"
            description="No Cellebrite reports have been imported for this case."
          />
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)_360px] overflow-hidden">
          <ReportRail
            reports={reports}
            selectedKeys={activeReportKeys}
            onSelectedKeysChange={setSelectedKeys}
            caseId={caseId}
          />

          <main className="min-w-0 overflow-hidden">
            {activeTab === "overview" && (
              <OverviewTab
                active={activeTab === "overview"}
                caseId={caseId}
                query={query}
                reports={selectedReports}
                onSelect={setSelection}
                onFilterComms={(seed) => {
                  const seedReportKeys = seed.reportKeys?.length
                    ? seed.reportKeys
                    : seed.reportKey
                      ? [seed.reportKey]
                      : []
                  if (seedReportKeys.length) setSelectedKeys(seedReportKeys)
                  setCommsSeed(seed)
                  setActiveTab("comms")
                }}
              />
            )}
            {activeTab === "unified" && (
              <UnifiedContactsTab
                active={activeTab === "unified"}
                caseId={caseId}
                reportKeys={reportKeys}
                reports={selectedReports}
                query={query}
                onSelect={setSelection}
                onFilterComms={(seed) => {
                  const seedReportKeys = seed.reportKeys?.length
                    ? seed.reportKeys
                    : seed.reportKey
                      ? [seed.reportKey]
                      : []
                  if (seedReportKeys.length) setSelectedKeys(seedReportKeys)
                  setCommsSeed(seed)
                  setActiveTab("comms")
                }}
              />
            )}
            {activeTab === "comms" && (
              <CommsTab
                active={activeTab === "comms"}
                caseId={caseId}
                reportKeys={reportKeys}
                query={query}
                dateFilters={dateFilters}
                seed={commsSeed}
                onSelect={setSelection}
              />
            )}
            {activeTab === "events" && (
              <EventsTab
                active={activeTab === "events"}
                caseId={caseId}
                reportKeys={reportKeys}
                query={query}
                dateFilters={dateFilters}
                onSelect={setSelection}
              />
            )}
            {activeTab === "timeline" && (
              <TimelineTab
                active={activeTab === "timeline"}
                caseId={caseId}
                reportKeys={reportKeys}
                query={query}
                dateFilters={dateFilters}
                onSelect={setSelection}
              />
            )}
            {activeTab === "files" && (
              <FilesTab
                active={activeTab === "files"}
                caseId={caseId}
                reportKeys={reportKeys}
                query={query}
                onSelect={setSelection}
              />
            )}
            {activeTab === "graph" && (
              <GraphTab
                active={activeTab === "graph"}
                caseId={caseId}
                reportKeys={reportKeys}
                dateFilters={dateFilters}
                onSelect={setSelection}
              />
            )}
          </main>

          <SelectionPanel
            selection={selection}
            onClear={() => setSelection(null)}
            reports={reports}
            fallback={<DetailFallback />}
          />
        </div>
      )}
    </div>
  )
}

function DateInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
      {label}
      <Input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 w-36"
      />
    </label>
  )
}

function ReportRail({
  reports,
  selectedKeys,
  onSelectedKeysChange,
  caseId,
}: {
  reports: PhoneReport[]
  selectedKeys: string[]
  onSelectedKeysChange: (keys: string[]) => void
  caseId: string
}) {
  const patchReport = usePatchCellebriteReport(caseId)
  const deleteReport = useDeleteCellebriteReport(caseId)
  const allSelected = reports.length > 0 && selectedKeys.length === reports.length

  const toggleReport = (key: string) => {
    if (selectedKeys.includes(key)) {
      const next = selectedKeys.filter((item) => item !== key)
      onSelectedKeysChange(next.length ? next : reports.map(reportKey))
    } else {
      onSelectedKeysChange([...selectedKeys, key])
    }
  }

  const renameReport = (report: PhoneReport) => {
    const current = report.device_name_override || reportTitle(report)
    const next = window.prompt("Device name", current)
    if (next === null) return
    patchReport.mutate(
      { reportKey: report.report_key, deviceNameOverride: next.trim() || null },
      {
        onSuccess: () => toast.success("Phone report updated"),
        onError: (error) => toast.error(error.message),
      }
    )
  }

  const removeReport = (report: PhoneReport) => {
    if (!window.confirm(`Delete ${reportTitle(report)} from this case?`)) return
    deleteReport.mutate(report.report_key, {
      onSuccess: () => toast.success("Phone report deleted"),
      onError: (error) => toast.error(error.message),
    })
  }

  return (
    <aside className="min-h-0 border-r border-border bg-muted/20">
      <div className="flex h-11 items-center gap-2 border-b border-border px-3">
        <Filter className="size-4 text-muted-foreground" />
        <span className="text-xs font-semibold">Reports</span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-7 text-xs"
          onClick={() => onSelectedKeysChange(allSelected ? [reports[0]?.report_key].filter(Boolean) : reports.map(reportKey))}
        >
          {allSelected ? "One" : "All"}
        </Button>
      </div>
      <div className="h-[calc(100%-2.75rem)] overflow-y-auto p-2">
        <div className="space-y-2">
          {reports.map((report) => {
            const key = reportKey(report)
            const checked = selectedKeys.includes(key)
            const stats = isRecord(report.stats) ? report.stats : {}
            return (
              <div
                key={key}
                className={cn(
                  "rounded-md border bg-card p-2 transition-colors",
                  checked ? "border-amber-400" : "border-border hover:border-slate-300"
                )}
              >
                <button
                  type="button"
                  className="flex w-full items-start gap-2 text-left"
                  onClick={() => toggleReport(key)}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border",
                      checked ? "border-amber-500 bg-amber-500 text-white" : "border-border"
                    )}
                  >
                    {checked && <CheckCircle2 className="size-3" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{reportTitle(report)}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {report.phone_number || report.imei || report.evidence_number || key}
                    </span>
                  </span>
                </button>
                <div className="mt-2 grid grid-cols-3 gap-1 text-[10px] text-muted-foreground">
                  <MiniStat label="Nodes" value={readNumber(stats, ["nodes", "node_count", "total_nodes"])} />
                  <MiniStat label="Msgs" value={readNumber(stats, ["messages", "message_count"])} />
                  <MiniStat label="Calls" value={readNumber(stats, ["calls", "call_count"])} />
                </div>
                <div className="mt-2 flex items-center gap-1">
                  <Button variant="ghost" size="icon-sm" onClick={() => renameReport(report)}>
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon-sm" onClick={() => removeReport(report)}>
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </aside>
  )
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border bg-muted/30 px-1.5 py-1">
      <div className="font-semibold text-foreground">{compactNumber(value)}</div>
      <div>{label}</div>
    </div>
  )
}

function CommsTab({
  active,
  caseId,
  reportKeys,
  query,
  dateFilters,
  seed,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  query: string
  dateFilters: DateFilters
  seed: CommsSeed | null
  onSelect: (selection: RailSelection) => void
}) {
  const [selectedThreadKey, setSelectedThreadKey] = useState<string | null>(null)
  const [type, setType] = useState<"all" | "message" | "call" | "email">(seed?.type ?? "all")
  const [sourceApp, setSourceApp] = useState("")
  const [participant, setParticipant] = useState(seed?.participantKeys.join(", ") ?? "")
  const participantKeys = useMemo(
    () => participant.split(",").map((value) => value.trim()).filter(Boolean),
    [participant]
  )

  const params = {
    reportKeys,
    startDate: dateFilters.startDate || null,
    endDate: dateFilters.endDate || null,
    search: query || null,
    sourceApps: sourceApp ? [sourceApp] : null,
    types: type === "all" ? null : [type],
    participantKeys: participantKeys.length ? participantKeys : null,
    limit: 200,
  }
  const threadsQuery = useCommsThreads(caseId, params, active)
  const sourceAppsQuery = useCommsSourceApps(caseId, reportKeys, active)
  const envelopeQuery = useCommsEnvelope(caseId, params, active)
  const searchQuery = useMessageSearch(caseId, { q: query, reportKeys, limit: 50 }, active && query.length > 1)
  const threads = useMemo(() => threadsQuery.data?.threads ?? [], [threadsQuery.data?.threads])
  const selectedThread = useMemo(
    () =>
      threads.find((thread) => `${thread.thread_type}:${thread.thread_id}` === selectedThreadKey) ??
      threads[0] ??
      null,
    [selectedThreadKey, threads]
  )
  const threadDetailQuery = useThreadDetail(
    caseId,
    selectedThread,
    { limit: 500 },
    active && !!selectedThread
  )

  return (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <TypeButton active={type === "all"} onClick={() => setType("all")}>All</TypeButton>
        <TypeButton active={type === "message"} onClick={() => setType("message")}>Messages</TypeButton>
        <TypeButton active={type === "call"} onClick={() => setType("call")}>Calls</TypeButton>
        <TypeButton active={type === "email"} onClick={() => setType("email")}>Emails</TypeButton>
        <select
          value={sourceApp}
          onChange={(event) => setSourceApp(event.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-xs"
        >
          <option value="">All apps</option>
          {(sourceAppsQuery.data?.apps ?? []).map((app) => {
            const label = app.source_app || app.app || app.name || "Unknown"
            return <option key={label} value={label}>{label}</option>
          })}
        </select>
        <Input
          value={participant}
          onChange={(event) => setParticipant(event.target.value)}
          placeholder="Participant key(s)"
          className="h-8 w-56"
        />
        {seed && participantKeys.length > 0 && (
          <Badge variant="amber">Filtered from Overview: {seed.label}</Badge>
        )}
        <Badge variant="slate" className="ml-auto">
          {compactNumber(envelopeQuery.data?.total)} records
        </Badge>
      </div>

      <div className="grid min-h-0 grid-cols-[320px_minmax(0,1fr)_320px] overflow-hidden">
        <div className="border-r border-border">
          <PaneHeader title="Threads" count={threadsQuery.data?.total ?? threads.length} loading={threadsQuery.isLoading} />
          <div className="h-[calc(100%-2.75rem)] overflow-y-auto p-2">
            {threads.map((thread) => (
              <button
                key={`${thread.thread_type}-${thread.thread_id}`}
                type="button"
                onClick={() => setSelectedThreadKey(`${thread.thread_type}:${thread.thread_id}`)}
                className={cn(
                  "mb-1 w-full rounded-md border p-2 text-left transition-colors",
                  selectedThread?.thread_id === thread.thread_id
                    ? "border-amber-400 bg-amber-50 dark:bg-amber-950/20"
                    : "border-border bg-card hover:bg-muted/50"
                )}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare className="size-3.5 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">
                    {thread.name || thread.thread_id}
                  </span>
                  <Badge variant="outline">{thread.thread_type}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">
                  {compactDate(thread.last_activity)} - {compactNumber(thread.item_count ?? thread.message_count)} items
                </div>
              </button>
            ))}
            {!threadsQuery.isLoading && threads.length === 0 && <SmallEmpty label="No threads" />}
          </div>
        </div>

        <div className="min-w-0">
          <PaneHeader
            title={selectedThread?.name || selectedThread?.thread_id || "Thread"}
            count={threadDetailQuery.data?.total ?? (threadDetailQuery.data?.items ?? threadDetailQuery.data?.messages ?? []).length}
            loading={threadDetailQuery.isLoading}
          />
          <div className="h-[calc(100%-2.75rem)] overflow-y-auto p-3">
            <EventList
              items={(threadDetailQuery.data?.items ?? threadDetailQuery.data?.messages ?? []) as CommsItem[]}
              loading={threadDetailQuery.isLoading}
              emptyLabel="No thread items"
              onSelect={(item) =>
                onSelect({
                  id: itemKey(item, "message"),
                  kind: "message",
                  title: readText(item, ["subject", "body", "summary", "label"], "Message"),
                  payload: item,
                })
              }
            />
          </div>
        </div>

        <DetailColumn title="Search & Envelope">
          <Histogram rows={envelopeQuery.data?.histogram ?? []} />
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Message Matches
            </h3>
            <EventList
              items={searchQuery.data?.matches ?? []}
              loading={searchQuery.isLoading}
              emptyLabel={query.length > 1 ? "No matches" : "Enter a search"}
              onSelect={(item) =>
                onSelect({
                  id: itemKey(item, "match"),
                  kind: "message",
                  title: readText(item, ["subject", "body", "summary", "label"], "Message"),
                  payload: item,
                })
              }
            />
          </div>
        </DetailColumn>
      </div>
    </section>
  )
}

function EventsTab({
  active,
  caseId,
  reportKeys,
  query,
  dateFilters,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  query: string
  dateFilters: DateFilters
  onSelect: (selection: RailSelection) => void
}) {
  const [eventType, setEventType] = useState("")
  const [selectedEventKey, setSelectedEventKey] = useState<string | null>(null)
  const [onlyGeolocated, setOnlyGeolocated] = useState(false)
  const eventTypesQuery = useEventTypes(caseId, reportKeys, active)
  const eventsQuery = useEvents(
    caseId,
    {
      reportKeys,
      startDate: dateFilters.startDate || null,
      endDate: dateFilters.endDate || null,
      eventTypes: eventType ? [eventType] : null,
      onlyGeolocated,
      limit: 1000,
    },
    active
  )
  const tilesQuery = useLocationTiles(
    caseId,
    { reportKeys, startDate: dateFilters.startDate || null, endDate: dateFilters.endDate || null, zoom: 6 },
    active
  )
  const tracksQuery = useEventTracks(
    caseId,
    { reportKeys, startDate: dateFilters.startDate || null, endDate: dateFilters.endDate || null },
    active
  )
  const detailQuery = useEventDetail(caseId, selectedEventKey, active && !!selectedEventKey)
  const relatedQuery = useEventRelated(caseId, selectedEventKey, active && !!selectedEventKey)
  const events = useMemo(() => {
    const rows = eventsQuery.data?.events ?? []
    if (!query) return rows
    const needle = query.toLowerCase()
    return rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle))
  }, [eventsQuery.data?.events, query])

  return (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border p-2">
        <select
          value={eventType}
          onChange={(event) => setEventType(event.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-xs"
        >
          <option value="">All event types</option>
          {(eventTypesQuery.data?.types ?? []).map((item) => {
            const label = eventTypeLabel(item)
            return <option key={label} value={label}>{label}</option>
          })}
        </select>
        <Button
          variant={onlyGeolocated ? "secondary" : "outline"}
          size="sm"
          onClick={() => setOnlyGeolocated((value) => !value)}
        >
          <MapPin className="size-3.5" />
          Geolocated
        </Button>
        <Badge variant="slate" className="ml-auto">
          {compactNumber(events.length)} events
        </Badge>
      </div>

      <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_360px] overflow-hidden">
        <RecordsPane
          title="Events"
          loading={eventsQuery.isLoading}
          rows={events}
          emptyLabel="No events"
          columns={[
            { id: "time", label: "Time", get: (row) => compactDate(row.timestamp ?? row.datetime ?? row.time) },
            { id: "type", label: "Type", get: (row) => readText(row, ["event_type", "type", "label"], "-") },
            { id: "app", label: "App", get: (row) => readText(row, ["source_app", "app"], "-") },
            { id: "summary", label: "Summary", get: (row) => truncate(readText(row, ["summary", "label", "body", "name"], "-"), 110) },
          ]}
          selectedId={selectedEventKey ?? undefined}
          onSelect={(row) => {
            const key = itemKey(row, "event")
            setSelectedEventKey(key)
            onSelect({
              id: key,
              kind: "event",
              title: readText(row, ["summary", "label", "event_type", "type"], "Event"),
              payload: row,
            })
          }}
        />
        <DetailColumn title="Locations & Detail">
          <MetricGrid
            metrics={[
              ["Tiles", compactNumber(tilesQuery.data?.tiles?.length ?? 0)],
              ["Tracks", compactNumber(tracksQuery.data?.tracks?.length ?? 0)],
              ["Types", compactNumber(eventTypesQuery.data?.types?.length ?? 0)],
            ]}
          />
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Event Detail
            </h3>
            {detailQuery.isLoading ? (
              <InlineLoading />
            ) : detailQuery.data ? (
              <JsonBlock value={detailQuery.data} />
            ) : (
              <SmallEmpty label="Select an event" />
            )}
          </div>
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Related Activity
            </h3>
            <JsonBlock value={relatedQuery.data ?? {}} />
          </div>
        </DetailColumn>
      </div>
    </section>
  )
}

function TimelineTab({
  active,
  caseId,
  reportKeys,
  query,
  dateFilters,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  query: string
  dateFilters: DateFilters
  onSelect: (selection: RailSelection) => void
}) {
  const timelineQuery = useCellebriteTimeline(
    caseId,
    reportKeys,
    {
      startDate: dateFilters.startDate || null,
      endDate: dateFilters.endDate || null,
      limit: 500,
    },
    active
  )
  const items = useMemo(() => {
    const rows = timelineQuery.data?.events ?? timelineQuery.data?.items ?? []
    if (!query) return rows
    const needle = query.toLowerCase()
    return rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle))
  }, [timelineQuery.data?.events, timelineQuery.data?.items, query])

  return (
    <section className="h-full min-h-0 overflow-hidden">
      <RecordsPane
        title="Timeline"
        loading={timelineQuery.isLoading}
        rows={items}
        emptyLabel="No timeline rows"
        columns={[
          { id: "time", label: "Time", get: (row) => compactDate(row.timestamp ?? row.datetime ?? row.time) },
          { id: "type", label: "Type", get: (row) => readText(row, ["event_type", "type"], "-") },
          { id: "device", label: "Device", get: (row) => readText(row, ["device_name", "report_key", "device_report_key"], "-") },
          { id: "summary", label: "Summary", get: (row) => truncate(readText(row, ["summary", "label", "body", "name"], "-"), 140) },
        ]}
        onSelect={(row) =>
          onSelect({
            id: itemKey(row, "timeline"),
            kind: "event",
            title: readText(row, ["summary", "label", "event_type", "type"], "Timeline event"),
            payload: row,
          })
        }
      />
    </section>
  )
}

function FilesTab({
  active,
  caseId,
  reportKeys,
  query,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  query: string
  onSelect: (selection: RailSelection) => void
}) {
  const [category, setCategory] = useState("")
  const [groupBy, setGroupBy] = useState<"category" | "parent" | "app" | "path">("category")
  const filesQuery = useCellebriteFiles(
    caseId,
    {
      reportKeys,
      category: category || null,
      search: query || null,
      limit: 500,
    },
    active
  )
  const treeQuery = useCellebriteFilesTree(caseId, { reportKeys, groupBy }, active)
  const files = filesQuery.data?.files ?? []

  return (
    <section className="grid h-full min-h-0 grid-cols-[300px_minmax(0,1fr)] overflow-hidden">
      <div className="border-r border-border bg-muted/20">
        <div className="flex h-11 items-center gap-2 border-b border-border px-3">
          <FolderTree className="size-4 text-muted-foreground" />
          <span className="text-xs font-semibold">File Tree</span>
        </div>
        <div className="space-y-2 p-3">
          <select
            value={groupBy}
            onChange={(event) => setGroupBy(event.target.value as "category" | "parent" | "app" | "path")}
            className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs"
          >
            <option value="category">Category</option>
            <option value="parent">Parent</option>
            <option value="app">App</option>
            <option value="path">Path</option>
          </select>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs"
          >
            <option value="">All categories</option>
            {["Image", "Audio", "Video", "Text"].map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <div className="max-h-[calc(100vh-16rem)] overflow-y-auto rounded-md border border-border bg-card p-2">
            {treeQuery.isLoading ? <InlineLoading /> : <TreeNode node={treeQuery.data?.root} />}
          </div>
        </div>
      </div>
      <RecordsPane
        title="Files"
        loading={filesQuery.isLoading}
        rows={files}
        emptyLabel="No files"
        columns={[
          { id: "name", label: "Name", get: (row) => readText(row, ["original_filename", "filename", "name"], "-") },
          { id: "category", label: "Category", get: (row) => readText(row, ["cellebrite_category", "category", "type"], "-") },
          { id: "path", label: "Path", get: (row) => truncate(readText(row, ["stored_path", "device_path", "path"], "-"), 90) },
          { id: "tags", label: "Tags", get: (row) => readList(row, ["tags"]).join(", ") || "-" },
        ]}
        onSelect={(row) =>
          onSelect({
            id: itemKey(row, "file"),
            kind: "file",
            title: readText(row, ["original_filename", "filename", "name"], "File"),
            payload: row,
          })
        }
      />
    </section>
  )
}

function GraphTab({
  active,
  caseId,
  reportKeys,
  dateFilters,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  dateFilters: DateFilters
  onSelect: (selection: RailSelection) => void
}) {
  const graphQuery = useCellebriteCrossPhoneGraph(caseId, active)
  const networkQuery = useCellebriteCommunicationNetwork(caseId, active)
  const intersections = useRunIntersections(caseId)
  const [methods, setMethods] = useState<string[]>(["spatial", "comm_hub"])
  const nodes = graphQuery.data?.nodes ?? []
  const links = graphQuery.data?.links ?? graphQuery.data?.edges ?? []
  const sharedContacts = graphQuery.data?.shared_contacts ?? networkQuery.data?.shared_contacts ?? []

  const run = () => {
    intersections.mutate(
      {
        methods,
        reportKeys,
        startDate: dateFilters.startDate || null,
        endDate: dateFilters.endDate || null,
      },
      {
        onError: (error) => toast.error(error.message),
      }
    )
  }

  return (
    <section className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_380px] overflow-hidden">
      <div className="min-w-0 overflow-y-auto p-3">
        <div className="h-[420px] rounded-md border border-border bg-card">
          {graphQuery.isLoading ? (
            <div className="flex h-full items-center justify-center"><LoadingSpinner /></div>
          ) : (
            <MiniGraph
              nodes={nodes}
              links={links}
              onNodeSelect={(node) =>
                onSelect({
                  id: readText(node, ["id", "key"], "node"),
                  kind: "event",
                  title: readText(node, ["label", "name", "id", "key"], "Node"),
                  payload: node,
                })
              }
            />
          )}
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <MetricCard icon={Network} label="Nodes" value={compactNumber(nodes.length)} />
          <MetricCard icon={GitBranch} label="Links" value={compactNumber(links.length)} />
          <MetricCard icon={Users} label="Shared" value={compactNumber(sharedContacts.length)} />
        </div>
        <div className="mt-3">
          <RecordsPane
            title="Shared Contacts"
            loading={networkQuery.isLoading}
            rows={sharedContacts}
            emptyLabel="No shared contacts"
            columns={[
              { id: "name", label: "Name", get: (row) => readText(row, ["name", "display_name", "label", "phone"], "-") },
              { id: "reports", label: "Reports", get: (row) => readList(row, ["report_keys", "devices"]).join(", ") || "-" },
              { id: "count", label: "Count", className: "text-right", get: (row) => compactNumber(readNumber(row, ["count", "message_count", "total"])) },
            ]}
            onSelect={(row) =>
              onSelect({
                id: itemKey(row, "shared"),
                kind: "contact",
                title: readText(row, ["name", "display_name", "label", "phone"], "Shared contact"),
                payload: row,
              })
            }
          />
        </div>
      </div>
      <DetailColumn title="Intersections">
        <div className="space-y-2">
          {INTERSECTION_METHODS.map((method) => (
            <label key={method} className="flex items-center gap-2 rounded-md border border-border bg-card px-2 py-1.5 text-sm">
              <input
                type="checkbox"
                checked={methods.includes(method)}
                onChange={(event) =>
                  setMethods((current) =>
                    event.target.checked
                      ? [...current, method]
                      : current.filter((item) => item !== method)
                  )
                }
              />
              <span className="font-medium">{method}</span>
            </label>
          ))}
          <Button size="sm" onClick={run} disabled={methods.length === 0 || intersections.isPending}>
            {intersections.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            Run
          </Button>
        </div>
        <div className="mt-4 space-y-2">
          {(intersections.data?.results ?? []).map((result, index) => {
            const row = isRecord(result) ? result : {}
            const matches = Array.isArray(row.matches) ? row.matches : []
            return (
              <div key={`${readText(row, ["method"], "method")}-${index}`} className="rounded-md border border-border bg-card p-2">
                <div className="flex items-center gap-2">
                  <Activity className="size-3.5 text-amber-500" />
                  <span className="text-sm font-semibold">{readText(row, ["method"], "Method")}</span>
                  <Badge variant="slate" className="ml-auto">{matches.length}</Badge>
                </div>
                {readText(row, ["reason"]) && (
                  <p className="mt-1 text-xs text-muted-foreground">{readText(row, ["reason"])}</p>
                )}
                <JsonBlock value={matches.slice(0, 5)} />
              </div>
            )
          })}
        </div>
      </DetailColumn>
    </section>
  )
}

function RecordsPane({
  title,
  loading,
  rows,
  columns,
  emptyLabel,
  selectedId,
  onSelect,
}: {
  title: string
  loading: boolean
  rows: CellebriteRecord[]
  columns: Column[]
  emptyLabel: string
  selectedId?: string
  onSelect?: (row: CellebriteRecord) => void
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <PaneHeader title={title} count={rows.length} loading={loading} />
      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="flex h-full items-center justify-center"><LoadingSpinner /></div>
        ) : rows.length === 0 ? (
          <SmallEmpty label={emptyLabel} />
        ) : (
          <table className="w-full table-fixed text-left text-sm">
            <thead className="sticky top-0 z-10 bg-muted text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                {columns.map((column) => (
                  <th key={column.id} className={cn("border-b border-border px-3 py-2 font-semibold", column.className)}>
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const key = itemKey(row, `${title}-${index}`)
                const selected = selectedId === key
                return (
                  <tr
                    key={`${key}-${index}`}
                    className={cn(
                      "border-b border-border/70 transition-colors",
                      onSelect && "cursor-pointer hover:bg-muted/50",
                      selected && "bg-amber-50 dark:bg-amber-950/20"
                    )}
                    onClick={() => onSelect?.(row)}
                  >
                    {columns.map((column) => (
                      <td key={column.id} className={cn("truncate px-3 py-2 align-top", column.className)}>
                        {column.get(row)}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
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

function DetailColumn({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-border bg-muted/20 p-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      <div className="mt-3">{children}</div>
    </aside>
  )
}

function SelectionPanel({
  selection,
  onClear,
  reports,
  fallback,
}: {
  selection: RailSelection | null
  onClear: () => void
  reports: PhoneReport[]
  fallback: ReactNode
}) {
  if (!selection) return <aside className="min-h-0 overflow-y-auto border-l border-border bg-muted/20">{fallback}</aside>

  return (
    <aside className="min-h-0 overflow-y-auto border-l border-border bg-muted/20">
      <div className="flex h-11 items-center gap-2 border-b border-border bg-card px-3">
        <span className="min-w-0 flex-1 truncate text-xs font-semibold">{selection.title}</span>
        <Badge variant="outline">{selection.kind}</Badge>
        <Button variant="ghost" size="icon-sm" onClick={onClear}>
          <X className="size-3.5" />
        </Button>
      </div>
      <div className="p-3">
        {selection.kind === "contact_unified" ? (
          <UnifiedContactDetail contact={selection.payload} reports={reports} />
        ) : (
          <JsonBlock value={selection.payload} />
        )}
      </div>
    </aside>
  )
}

function DetailFallback() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <SmallEmpty label="Select a record to inspect details" />
    </div>
  )
}

function EventList({
  items,
  loading,
  emptyLabel,
  onSelect,
}: {
  items: TimelineItem[]
  loading: boolean
  emptyLabel: string
  onSelect: (item: TimelineItem) => void
}) {
  if (loading) return <InlineLoading />
  if (items.length === 0) return <SmallEmpty label={emptyLabel} />
  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <button
          key={`${itemKey(item, "item")}-${index}`}
          type="button"
          onClick={() => onSelect(item)}
          className="w-full rounded-md border border-border bg-card p-2 text-left transition-colors hover:bg-muted/50"
        >
          <div className="flex items-center gap-2">
            <Badge variant="outline">{readText(item, ["type", "event_type", "thread_type"], "item")}</Badge>
            <span className="truncate text-xs text-muted-foreground">{compactDate(item.timestamp)}</span>
          </div>
          <div className="mt-1 truncate text-sm font-medium">
            {readText(item, ["subject", "summary", "label", "body", "name"], "Untitled")}
          </div>
          <div className="mt-1 truncate text-[11px] text-muted-foreground">
            {readText(item, ["source_app", "direction", "report_key", "device_report_key"], "-")}
          </div>
        </button>
      ))}
    </div>
  )
}

function TypeButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <Button variant={active ? "secondary" : "outline"} size="sm" onClick={onClick}>
      {children}
    </Button>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Smartphone
  label: string
  value: string
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="size-4 text-amber-500" />
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  )
}

function MetricGrid({ metrics }: { metrics: [string, string][] }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {metrics.map(([label, value]) => (
        <div key={label} className="rounded-md border border-border bg-card p-2">
          <div className="text-[11px] text-muted-foreground">{label}</div>
          <div className="mt-1 text-base font-semibold">{value}</div>
        </div>
      ))}
    </div>
  )
}

function Histogram({ rows }: { rows: { date: string; count: number }[] }) {
  if (rows.length === 0) return <SmallEmpty label="No histogram" />
  const max = Math.max(...rows.map((row) => row.count), 1)
  return (
    <div className="flex h-24 items-end gap-1 rounded-md border border-border bg-card p-2">
      {rows.slice(-36).map((row) => (
        <div key={row.date} className="flex min-w-1 flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-t bg-amber-500"
            style={{ height: `${Math.max(4, (row.count / max) * 72)}px` }}
            title={`${row.date}: ${row.count}`}
          />
        </div>
      ))}
    </div>
  )
}

function MiniGraph({
  nodes,
  links,
  onNodeSelect,
}: {
  nodes: GraphNode[]
  links: GraphLink[]
  onNodeSelect: (node: GraphNode) => void
}) {
  const visibleNodes = nodes.slice(0, 32)
  const positions = new Map<string, { x: number; y: number }>()
  const width = 800
  const height = 420
  const radius = 150
  visibleNodes.forEach((node, index) => {
    const angle = (index / Math.max(visibleNodes.length, 1)) * Math.PI * 2 - Math.PI / 2
    const id = graphNodeId(node)
    positions.set(id, {
      x: width / 2 + Math.cos(angle) * radius,
      y: height / 2 + Math.sin(angle) * radius,
    })
  })

  if (visibleNodes.length === 0) {
    return <SmallEmpty label="No graph nodes" />
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full">
      <rect width={width} height={height} className="fill-background" />
      {links.slice(0, 120).map((link, index) => {
        const source = positions.get(graphEndpointId(link.source))
        const target = positions.get(graphEndpointId(link.target))
        if (!source || !target) return null
        return (
          <line
            key={`${graphEndpointId(link.source)}-${graphEndpointId(link.target)}-${index}`}
            x1={source.x}
            y1={source.y}
            x2={target.x}
            y2={target.y}
            className="stroke-slate-300 dark:stroke-slate-700"
            strokeWidth={Math.max(1, Math.min(6, Number(link.weight) || 1))}
          />
        )
      })}
      {visibleNodes.map((node) => {
        const id = graphNodeId(node)
        const position = positions.get(id)
        if (!position) return null
        return (
          <g key={id} role="button" className="cursor-pointer" onClick={() => onNodeSelect(node)}>
            <circle cx={position.x} cy={position.y} r="18" className="fill-amber-500 stroke-background" strokeWidth="3" />
            <text x={position.x} y={position.y + 34} textAnchor="middle" className="fill-foreground text-[11px]">
              {truncate(readText(node, ["label", "name", "id", "key"], id), 18)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function graphNodeId(node: GraphNode): string {
  return readText(node, ["id", "key", "label", "name"], "node")
}

function graphEndpointId(value: string | GraphNode | undefined): string {
  return typeof value === "string" ? value : value ? graphNodeId(value) : ""
}

function TreeNode({ node, depth = 0 }: { node?: FileTreeNode; depth?: number }) {
  if (!node) return <SmallEmpty label="No tree" />
  return (
    <div>
      <div className="flex items-center gap-2 py-1 text-xs" style={{ paddingLeft: `${depth * 12}px` }}>
        <FolderTree className="size-3.5 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate">{node.label}</span>
        <Badge variant="outline">{node.count}</Badge>
      </div>
      {(node.children ?? []).slice(0, 80).map((child) => (
        <TreeNode key={`${child.label}-${depth}`} node={child} depth={depth + 1} />
      ))}
    </div>
  )
}

function InlineLoading() {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" />
      Loading
    </div>
  )
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border bg-card p-2 text-[11px] leading-relaxed text-muted-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function eventTypeLabel(item: EventTypeCount): string {
  return readText(item, ["event_type", "type", "label"], "Unknown")
}
