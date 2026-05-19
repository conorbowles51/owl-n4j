import { useMemo, useState, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import {
  CheckCircle2,
  Clock,
  Filter,
  FolderTree,
  Globe,
  MapPin,
  MessageSquare,
  Network,
  Pencil,
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
  useCellebriteReports,
  useDeleteCellebriteReport,
  usePatchCellebriteReport,
} from "../hooks/use-cellebrite"
import type { CellebriteTabKey, PhoneReport, RailSelection } from "../types"
import { CommsTab } from "./comms/CommsTab"
import { EventsTab } from "./events/EventsTab"
import { FilesTab } from "./files/FilesTab"
import { GraphTab } from "./graph/GraphTab"
import { LocationTileDetail } from "./locations/LocationTileDetail"
import { LocationsTab } from "./locations/LocationsTab"
import { OverviewTab } from "./overview/OverviewTab"
import { TimelineTab } from "./timeline/TimelineTab"
import { UnifiedContactsTab } from "./unified/UnifiedContactsTab"
import { UnifiedContactDetail } from "./unified/UnifiedContactDetail"
import { SmallEmpty } from "./shared/SmallEmpty"
import {
  compactNumber,
  isRecord,
  readNumber,
  reportKey,
  reportTitle,
  selectedReportParams,
} from "./shared/cellebrite-format"
import type { CommsSeed } from "./shared/cellebrite-types"
import { CommunicationsTab } from "./communications/CommunicationsTab"

type TabDef = {
  key: CellebriteTabKey
  label: string
  icon: typeof Smartphone
}

type DateFilters = {
  startDate: string
  endDate: string
}

const TABS: TabDef[] = [
  { key: "overview", label: "Overview", icon: Smartphone },
  { key: "comms", label: "Comms Center", icon: MessageSquare },
  { key: "locations", label: "Locations", icon: Globe },
  { key: "events", label: "Location & Events", icon: MapPin },
  { key: "files", label: "Files", icon: FolderTree },
  { key: "graph", label: "Cross-Phone Graph", icon: Network },
  { key: "timeline", label: "Timeline", icon: Clock },
  { key: "communications", label: "Communications", icon: Users },
  { key: "unified", label: "Unified Contacts", icon: UserRound },
]

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
  const reports = useMemo(
    () => reportsQuery.data?.reports ?? [],
    [reportsQuery.data?.reports]
  )
  const allReportKeys = useMemo(
    () => reports.map(reportKey).filter(Boolean),
    [reports]
  )
  const activeReportKeys = useMemo(() => {
    const kept = selectedKeys.filter((key) => allReportKeys.includes(key))
    return kept.length > 0 ? kept : allReportKeys
  }, [allReportKeys, selectedKeys])

  const selectedReports = useMemo(
    () =>
      reports.filter((report) => activeReportKeys.includes(reportKey(report))),
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
              <h1 className="text-sm font-semibold text-foreground">
                Cellebrite Phone Viewer
              </h1>
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => reportsQuery.refetch()}
            >
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
            onChange={(startDate) =>
              setDateFilters((current) => ({ ...current, startDate }))
            }
          />
          <DateInput
            label="End"
            value={dateFilters.endDate}
            onChange={(endDate) =>
              setDateFilters((current) => ({ ...current, endDate }))
            }
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
                reports={selectedReports}
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
                reports={selectedReports}
                query={query}
                dateFilters={dateFilters}
                onSelect={setSelection}
              />
            )}
            {activeTab === "locations" && (
              <LocationsTab
                active={activeTab === "locations"}
                caseId={caseId}
                reportKeys={reportKeys}
                reports={selectedReports}
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
                reports={selectedReports}
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
                reports={selectedReports}
                query={query}
                onSelect={setSelection}
              />
            )}
            {activeTab === "graph" && (
              <GraphTab
                active={activeTab === "graph"}
                caseId={caseId}
                reportKeys={reportKeys}
                reports={selectedReports}
                dateFilters={dateFilters}
                onSelect={setSelection}
              />
            )}
            {activeTab === "communications" && (
              <CommunicationsTab
                active={activeTab === "communications"}
                caseId={caseId}
                reportKeys={reportKeys}
                reports={selectedReports}
                query={query}
                onSelect={setSelection}
              />
            )}
          </main>

          <SelectionPanel
            caseId={caseId}
            selection={selection}
            onSelect={setSelection}
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
  const allSelected =
    reports.length > 0 && selectedKeys.length === reports.length

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
          onClick={() =>
            onSelectedKeysChange(
              allSelected
                ? [reports[0]?.report_key].filter(Boolean)
                : reports.map(reportKey)
            )
          }
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
                  checked
                    ? "border-amber-400"
                    : "border-border hover:border-slate-300"
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
                      checked
                        ? "border-amber-500 bg-amber-500 text-white"
                        : "border-border"
                    )}
                  >
                    {checked && <CheckCircle2 className="size-3" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">
                      {reportTitle(report)}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {report.phone_number ||
                        report.imei ||
                        report.evidence_number ||
                        key}
                    </span>
                  </span>
                </button>
                <div className="mt-2 grid grid-cols-3 gap-1 text-[10px] text-muted-foreground">
                  <MiniStat
                    label="Nodes"
                    value={readNumber(stats, [
                      "nodes",
                      "node_count",
                      "total_nodes",
                    ])}
                  />
                  <MiniStat
                    label="Msgs"
                    value={readNumber(stats, ["messages", "message_count"])}
                  />
                  <MiniStat
                    label="Calls"
                    value={readNumber(stats, ["calls", "call_count"])}
                  />
                </div>
                <div className="mt-2 flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => renameReport(report)}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => removeReport(report)}
                  >
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
      <div className="font-semibold text-foreground">
        {compactNumber(value)}
      </div>
      <div>{label}</div>
    </div>
  )
}

function SelectionPanel({
  caseId,
  selection,
  onSelect,
  onClear,
  reports,
  fallback,
}: {
  caseId: string
  selection: RailSelection | null
  onSelect: (selection: RailSelection) => void
  onClear: () => void
  reports: PhoneReport[]
  fallback: ReactNode
}) {
  if (!selection)
    return (
      <aside className="min-h-0 overflow-y-auto border-l border-border bg-muted/20">
        {fallback}
      </aside>
    )

  return (
    <aside className="min-h-0 overflow-y-auto border-l border-border bg-muted/20">
      <div className="flex h-11 items-center gap-2 border-b border-border bg-card px-3">
        <span className="min-w-0 flex-1 truncate text-xs font-semibold">
          {selection.title}
        </span>
        <Badge variant="outline">{selection.kind}</Badge>
        <Button variant="ghost" size="icon-sm" onClick={onClear}>
          <X className="size-3.5" />
        </Button>
      </div>
      <div className="p-3">
        {selection.kind === "contact_unified" ? (
          <UnifiedContactDetail contact={selection.payload} reports={reports} />
        ) : selection.kind === "tile" ? (
          <LocationTileDetail
            caseId={caseId}
            payload={selection.payload}
            reports={reports}
            onSelectLocation={(location) =>
              onSelect({
                id: String(
                  location.id ?? location.node_key ?? location.key ?? "location"
                ),
                kind: "event",
                title: String(
                  location.label ??
                    location.location_type ??
                    location.address ??
                    "Location"
                ),
                payload: { ...location, event_type: "location" },
              })
            }
          />
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

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border bg-card p-2 text-[11px] leading-relaxed text-muted-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}
