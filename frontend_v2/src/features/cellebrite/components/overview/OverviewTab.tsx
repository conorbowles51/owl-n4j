import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import MaplibreMap, { Layer, NavigationControl, Source } from "react-map-gl/maplibre"
import maplibregl from "maplibre-gl"
import type { MapLayerMouseEvent, MapRef } from "react-map-gl/maplibre"
import {
  AlertTriangle,
  ArrowDown,
  ArrowDownLeft,
  ArrowLeft,
  ArrowUp,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Filter,
  Folder,
  Hash,
  Loader2,
  Mail,
  MapPin,
  MessageSquare,
  Paperclip,
  Pencil,
  Phone,
  PhoneIncoming,
  PhoneMissed,
  PhoneOutgoing,
  Route,
  Search,
  Shield,
  Smartphone,
  Trash2,
  UserRound,
  Video,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { useMapTheme } from "@/features/map/hooks/use-map-theme"
import { cn } from "@/lib/cn"
import {
  useDeleteCellebriteReport,
  useOverviewRows,
  usePatchCellebriteReport,
} from "../../hooks/use-cellebrite"
import type { CellebriteRecord, OverviewKind, PhoneReport, RailSelection } from "../../types"
import type { CommsSeed } from "../shared/cellebrite-types"
import { SmallEmpty } from "../shared/SmallEmpty"
import {
  asText,
  compactDate,
  compactNumber,
  isRecord,
  itemKey,
  readList,
  readNumber,
  readText,
  reportTitle,
  truncate,
} from "../shared/cellebrite-format"

const OVERVIEW_KINDS: { kind: OverviewKind; label: string }[] = [
  { kind: "contacts", label: "Contacts" },
  { kind: "messages", label: "Messages" },
  { kind: "calls", label: "Calls" },
  { kind: "locations", label: "Locations" },
  { kind: "emails", label: "Emails" },
]

export function OverviewTab({
  active,
  caseId,
  query,
  reports,
  onSelect,
  onFilterComms,
}: {
  active: boolean
  caseId: string
  query: string
  reports: PhoneReport[]
  onSelect: (selection: RailSelection) => void
  onFilterComms: (seed: CommsSeed) => void
}) {
  const [drillDown, setDrillDown] = useState<OverviewDrillDown | null>(null)
  const patchReport = usePatchCellebriteReport(caseId)
  const deleteReport = useDeleteCellebriteReport(caseId)
  const visibleDrillDown = drillDown && reports.some((report) => report.report_key === drillDown.report.report_key)
    ? drillDown
    : null

  const renameReport = useCallback(
    async (report: PhoneReport) => {
      const nextName = window.prompt("Device name", report.device_name_override || reportTitle(report))
      if (nextName === null) return
      try {
        await patchReport.mutateAsync({
          reportKey: report.report_key,
          deviceNameOverride: nextName.trim() || null,
        })
        toast.success("Device name updated")
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to update device name")
      }
    },
    [patchReport]
  )

  const removeReport = useCallback(
    async (report: PhoneReport) => {
      const total = overviewTotalComms(report)
      const confirmed = window.confirm(
        `Delete ${reportTitle(report)} and ${compactNumber(total)} related records from this case? This cannot be undone.`
      )
      if (!confirmed) return
      try {
        await deleteReport.mutateAsync(report.report_key)
        toast.success("Phone report deleted")
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to delete report")
      }
    },
    [deleteReport]
  )

  if (!reports.length) {
    return (
      <section className="flex h-full items-center justify-center">
        <SmallEmpty label="No phone reports available" />
      </section>
    )
  }

  if (visibleDrillDown) {
    return (
      <OverviewDrilldownView
        key={`${visibleDrillDown.report.report_key}-${visibleDrillDown.kind}`}
        active={active}
        caseId={caseId}
        query={query}
        drillDown={visibleDrillDown}
        onBack={() => setDrillDown(null)}
        onSelect={onSelect}
        onFilterComms={onFilterComms}
      />
    )
  }

  return (
    <section className="h-full overflow-y-auto p-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        {reports.map((report) => (
          <OverviewDeviceCard
            key={report.report_key}
            report={report}
            onDrillDown={(kind) => setDrillDown({ kind, report })}
            onRename={() => renameReport(report)}
            onDelete={() => removeReport(report)}
          />
        ))}
      </div>
    </section>
  )
}

type OverviewDrillDown = {
  kind: OverviewKind
  report: PhoneReport
}

type OverviewSort = {
  key: string
  dir: "asc" | "desc"
}

type OverviewDetailColumn = {
  key: string
  label: string
  width: string
  align?: "left" | "right"
  sortable?: boolean
  getSortValue?: (row: CellebriteRecord) => string | number | boolean | null | undefined
  render: (row: CellebriteRecord) => ReactNode
}

function OverviewDeviceCard({
  report,
  onDrillDown,
  onRename,
  onDelete,
}: {
  report: PhoneReport
  onDrillDown: (kind: OverviewKind) => void
  onRename: () => void
  onDelete: () => void
}) {
  const customName = Boolean(report.device_name_override)
  const ownerName = report.phone_owner_name || report.owner_name
  const phoneNumbers = readList(report, ["phone_numbers", "phone_number"])
  const extractionType = readText(report, ["extraction_type", "extraction_method"])
  const caseNumber = readText(report, ["case_number"])
  const examiner = readText(report, ["examiner"])

  return (
    <article className="overflow-hidden rounded-md border border-border bg-card shadow-sm transition-shadow hover:shadow-md">
      <div className="border-b border-border bg-emerald-50/60 p-4 dark:bg-emerald-950/10">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md border border-emerald-200 bg-emerald-100 dark:border-emerald-900 dark:bg-emerald-950/50">
            <Smartphone className="size-5 text-emerald-700 dark:text-emerald-300" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h3 className="truncate text-sm font-semibold text-foreground">
                {reportTitle(report)}
              </h3>
              {customName && (
                <Badge variant="warning" className="h-5 px-1.5 text-[9px] uppercase">
                  Custom
                </Badge>
              )}
              <Button variant="ghost" size="icon-sm" title="Edit device name" onClick={onRename}>
                <Pencil className="size-3.5" />
              </Button>
            </div>
            {ownerName && (
              <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                <UserRound className="size-3.5" />
                <span className="truncate">{ownerName}</span>
              </div>
            )}
          </div>
          <Button variant="ghost" size="icon-sm" title="Delete this phone report" onClick={onDelete}>
            <Trash2 className="size-4 text-muted-foreground hover:text-destructive" />
          </Button>
        </div>
      </div>

      <div className="space-y-2 p-4">
        {phoneNumbers.length > 0 && <OverviewInfoRow icon={Phone} label="Phone" value={phoneNumbers.join(", ")} />}
        {report.imei && <OverviewInfoRow icon={Hash} label="IMEI" value={asText(report.imei)} />}
        {extractionType && <OverviewInfoRow icon={Shield} label="Extract" value={extractionType} />}
        {caseNumber && <OverviewInfoRow icon={Hash} label="Case #" value={caseNumber} />}
        {examiner && <OverviewInfoRow icon={UserRound} label="Examiner" value={examiner} />}
      </div>

      <div className="px-4 pb-4">
        <div className="grid grid-cols-3 gap-2">
          {OVERVIEW_KINDS.map(({ kind, label }) => {
            const meta = overviewKindMeta(kind)
            return (
              <OverviewStatTile
                key={kind}
                icon={meta.icon}
                count={overviewStatCount(report, kind)}
                label={label}
                tone={kind}
                onClick={() => onDrillDown(kind)}
              />
            )
          })}
          <OverviewStatTile
            icon={MessageSquare}
            count={overviewTotalComms(report)}
            label="Total Comms"
            tone="total"
          />
        </div>
      </div>

      <OverviewReconciliationPanel reconciliation={report.reconciliation} />
    </article>
  )
}

function OverviewInfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Smartphone
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Icon className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="w-16 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate font-medium text-foreground">{value}</span>
    </div>
  )
}

function OverviewStatTile({
  icon: Icon,
  count,
  label,
  tone,
  onClick,
}: {
  icon: typeof Smartphone
  count: number
  label: string
  tone: OverviewKind | "total"
  onClick?: () => void
}) {
  const content = (
    <>
      <Icon className="mx-auto size-3.5 opacity-80" />
      <div className="mt-1 text-sm font-semibold tabular-nums">{compactNumber(count)}</div>
      <div className="text-[10px] opacity-75">
        {label}
        {onClick ? " >" : ""}
      </div>
    </>
  )
  const className = cn(
    "rounded-md border p-2 text-center text-xs transition-all",
    overviewToneClass(tone),
    onClick && "hover:shadow-sm hover:ring-2 hover:ring-current/20 active:scale-[0.98]"
  )
  if (!onClick) return <div className={className}>{content}</div>
  return (
    <button type="button" className={className} onClick={onClick} title={`Browse ${label.toLowerCase()}`}>
      {content}
    </button>
  )
}

function OverviewReconciliationPanel({ reconciliation }: { reconciliation: unknown }) {
  const data = isRecord(reconciliation) ? reconciliation : null
  const summary = isRecord(data?.summary) ? data.summary : {}
  const rows = Array.isArray(data?.rows) ? data.rows.filter(isRecord) : []
  const hasIssues = readNumber(summary, ["types_under"]) > 0
  const hasUnknown = readNumber(summary, ["types_not_supported"]) > 0
  const [open, setOpen] = useState(hasIssues)

  if (rows.length === 0) return null

  const totalXml = readNumber(summary, ["total_xml_models"])

  return (
    <div className="border-t border-border px-4 py-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 text-left text-muted-foreground transition-colors hover:text-foreground"
      >
        <span className="flex min-w-0 items-center gap-1.5">
          {hasIssues ? (
            <AlertTriangle className="size-3.5 shrink-0 text-amber-600" />
          ) : (
            <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600" />
          )}
          <span className="truncate font-medium">
            {hasIssues
              ? `Reconciliation: ${readNumber(summary, ["types_under"])} type${readNumber(summary, ["types_under"]) === 1 ? "" : "s"} under-persisted`
              : "Reconciliation: all counts match"}
          </span>
          <span className="hidden shrink-0 text-muted-foreground xl:inline">
            ({compactNumber(totalXml)} XML models, {compactNumber(rows.length)} types)
          </span>
        </span>
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
      </button>

      {open && (
        <div className="mt-2 max-h-48 overflow-auto rounded-md border border-border">
          <table className="w-full text-[11px]">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="px-2 py-1 text-left font-medium">Model type</th>
                <th className="px-2 py-1 text-right font-medium">XML</th>
                <th className="px-2 py-1 text-right font-medium">Persisted</th>
                <th className="px-2 py-1 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <OverviewReconciliationRow key={readText(row, ["model_type"], JSON.stringify(row))} row={row} />
              ))}
            </tbody>
          </table>
          {hasUnknown && (
            <div className="border-t border-border bg-muted/50 px-2 py-1 text-[10px] text-muted-foreground">
              Not supported types are present in the XML but are not yet persisted by the parser.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function OverviewReconciliationRow({ row }: { row: CellebriteRecord }) {
  const status = readText(row, ["status"], "ok")
  return (
    <tr className="border-t border-border/70">
      <td className="px-2 py-1 font-mono text-foreground">{readText(row, ["model_type"], "-")}</td>
      <td className="px-2 py-1 text-right tabular-nums">{compactNumber(readNumber(row, ["xml_count"]))}</td>
      <td className="px-2 py-1 text-right tabular-nums">{compactNumber(readNumber(row, ["persisted_count"]))}</td>
      <td className="px-2 py-1">
        <span className={cn("rounded px-1.5 py-px text-[10px] uppercase", reconciliationStatusClass(status))}>
          {status === "not_supported" ? "not supported" : status}
        </span>
      </td>
    </tr>
  )
}

function OverviewDrilldownView({
  active,
  caseId,
  query,
  drillDown,
  onBack,
  onSelect,
  onFilterComms,
}: {
  active: boolean
  caseId: string
  query: string
  drillDown: OverviewDrillDown
  onBack: () => void
  onSelect: (selection: RailSelection) => void
  onFilterComms: (seed: CommsSeed) => void
}) {
  const [search, setSearch] = useState(query)
  const [sort, setSort] = useState<OverviewSort>(() => overviewDefaultSort(drillDown.kind))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [trajectoryOn, setTrajectoryOn] = useState(false)
  const meta = overviewKindMeta(drillDown.kind)
  const rowsQuery = useOverviewRows(
    drillDown.kind,
    caseId,
    drillDown.report.report_key,
    { search: search || null, limit: drillDown.kind === "locations" ? 5000 : 1000 },
    active
  )
  const rows = useMemo(
    () => rowsForOverview(drillDown.kind, rowsQuery.data),
    [drillDown.kind, rowsQuery.data]
  )
  const columns = useMemo(
    () => overviewDetailColumns(drillDown.kind, caseId, drillDown.report, onFilterComms),
    [caseId, drillDown.kind, drillDown.report, onFilterComms]
  )
  const sortedRows = useMemo(
    () => sortOverviewRows(rows, columns, sort),
    [columns, rows, sort]
  )
  const total = rowsQuery.data?.total ?? rows.length

  const toggleSort = useCallback(
    (key: string) => {
      setSort((current) => ({
        key,
        dir: current.key === key && current.dir === "desc" ? "asc" : "desc",
      }))
    },
    []
  )

  const handleRowSelect = useCallback(
    (row: CellebriteRecord) => {
      const key = itemKey(row, `${drillDown.kind}-row`)
      setSelectedId(key)
      onSelect(overviewSelectionForRow(drillDown.kind, row, drillDown.report))
    },
    [drillDown.kind, drillDown.report, onSelect]
  )

  return (
    <section className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex min-h-12 shrink-0 items-center gap-3 border-b border-border bg-card px-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-3.5" />
          Back
        </Button>
        <div className="flex min-w-0 items-center gap-2 rounded-md border border-border bg-muted/40 px-2 py-1">
          <Smartphone className="size-3.5 shrink-0 text-emerald-600" />
          <span className="truncate text-xs font-semibold">{reportTitle(drillDown.report)}</span>
          {(drillDown.report.phone_owner_name || drillDown.report.owner_name) && (
            <>
              <span className="text-muted-foreground">/</span>
              <UserRound className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate text-xs text-muted-foreground">
                {drillDown.report.phone_owner_name || drillDown.report.owner_name}
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <meta.icon className="size-4 text-amber-500" />
          <span className="text-sm font-semibold">{meta.label}</span>
          <Badge variant="slate">{compactNumber(total)}</Badge>
        </div>
        <div className="relative ml-2 max-w-md flex-1">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search..."
            className="h-8 pl-7"
          />
        </div>
        {drillDown.kind === "locations" && (
          <Button
            variant={trajectoryOn ? "secondary" : "outline"}
            size="sm"
            onClick={() => {
              const next = !trajectoryOn
              setTrajectoryOn(next)
              if (next) setSort({ key: "timestamp", dir: "asc" })
            }}
          >
            <Route className="size-3.5" />
            {trajectoryOn ? "Trajectory on" : "Show trajectory"}
          </Button>
        )}
        {rowsQuery.isLoading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
        {rowsQuery.error && <span className="text-xs text-destructive">Failed to load</span>}
      </div>

      {drillDown.kind === "locations" ? (
        <OverviewLocationsDrilldown
          rows={sortedRows}
          columns={columns}
          selectedId={selectedId}
          loading={rowsQuery.isLoading}
          sort={sort}
          trajectoryOn={trajectoryOn}
          onSort={toggleSort}
          onSelect={handleRowSelect}
        />
      ) : (
        <OverviewVirtualTable
          rows={sortedRows}
          columns={columns}
          selectedId={selectedId}
          loading={rowsQuery.isLoading}
          emptyLabel={`No ${meta.label.toLowerCase()} found`}
          sort={sort}
          onSort={toggleSort}
          onSelect={handleRowSelect}
        />
      )}

      <div className="flex h-7 shrink-0 items-center justify-between border-t border-border bg-card px-3 text-[10px] text-muted-foreground">
        <span>
          Showing {compactNumber(sortedRows.length)} of {compactNumber(total)}
          {trajectoryOn && " / trajectory mode sorts oldest to newest"}
        </span>
        <span>
          Sorted by {sort.key} {sort.dir === "asc" ? "up" : "down"}
        </span>
      </div>
    </section>
  )
}

function OverviewLocationsDrilldown({
  rows,
  columns,
  selectedId,
  loading,
  sort,
  trajectoryOn,
  onSort,
  onSelect,
}: {
  rows: CellebriteRecord[]
  columns: OverviewDetailColumn[]
  selectedId: string | null
  loading: boolean
  sort: OverviewSort
  trajectoryOn: boolean
  onSort: (key: string) => void
  onSelect: (row: CellebriteRecord) => void
}) {
  return (
    <ResizablePanelGroup orientation="vertical" className="min-h-0 flex-1">
      <ResizablePanel defaultSize={55} minSize={20}>
        <OverviewLocationMap
          rows={rows}
          selectedId={selectedId}
          trajectoryOn={trajectoryOn}
          onSelect={onSelect}
        />
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel defaultSize={45} minSize={20}>
        <OverviewVirtualTable
          rows={rows}
          columns={columns}
          selectedId={selectedId}
          loading={loading}
          emptyLabel="No locations found"
          sort={sort}
          onSort={onSort}
          onSelect={onSelect}
        />
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}

function OverviewVirtualTable({
  rows,
  columns,
  selectedId,
  loading,
  emptyLabel,
  sort,
  onSort,
  onSelect,
}: {
  rows: CellebriteRecord[]
  columns: OverviewDetailColumn[]
  selectedId: string | null
  loading: boolean
  emptyLabel: string
  sort: OverviewSort
  onSort: (key: string) => void
  onSelect: (row: CellebriteRecord) => void
}) {
  const parentRef = useRef<HTMLDivElement | null>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(400)
  const rowHeight = 40
  const overscan = 8
  const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan)
  const visibleCount = Math.ceil(containerHeight / rowHeight) + overscan * 2
  const endIndex = Math.min(rows.length, startIndex + visibleCount)
  const visibleRows = rows.slice(startIndex, endIndex)
  const totalHeight = rows.length * rowHeight
  const gridTemplate = columns.map((column) => column.width).join(" ")

  useEffect(() => {
    const element = parentRef.current
    if (!element) return undefined
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setContainerHeight(entry.contentRect.height || 400)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className="grid h-8 shrink-0 border-b border-border bg-muted text-[11px] font-semibold uppercase text-muted-foreground"
        style={{ gridTemplateColumns: gridTemplate }}
      >
        {columns.map((column) => {
          const sortable = column.sortable !== false
          return (
            <button
              key={column.key}
              type="button"
              disabled={!sortable}
              onClick={() => sortable && onSort(column.key)}
              className={cn(
                "flex items-center gap-1 border-r border-border px-2 last:border-r-0",
                column.align === "right" ? "justify-end text-right" : "justify-start text-left",
                sortable && "hover:bg-muted-foreground/10",
                sort.key === column.key && "text-foreground"
              )}
            >
              <span className="truncate">{column.label}</span>
              {sort.key === column.key && (
                sort.dir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />
              )}
            </button>
          )
        })}
      </div>
      <div
        ref={parentRef}
        className="relative min-h-0 flex-1 overflow-auto"
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      >
        {loading ? (
          <div className="flex h-full items-center justify-center"><LoadingSpinner /></div>
        ) : rows.length === 0 ? (
          <SmallEmpty label={emptyLabel} />
        ) : (
          <div className="relative w-full" style={{ height: `${totalHeight}px` }}>
            {visibleRows.map((row, visibleIndex) => {
              const rowIndex = startIndex + visibleIndex
              const key = itemKey(row, `overview-${rowIndex}`)
              const selected = selectedId === key
              return (
                <div
                  key={`${key}-${rowIndex}`}
                  className={cn(
                    "absolute inset-x-0 grid cursor-pointer items-center border-b border-border/70 text-xs transition-colors hover:bg-muted/50",
                    selected && "bg-amber-50 dark:bg-amber-950/20"
                  )}
                  style={{
                    height: `${rowHeight}px`,
                    transform: `translateY(${rowIndex * rowHeight}px)`,
                    gridTemplateColumns: gridTemplate,
                  }}
                  onClick={() => onSelect(row)}
                >
                  {columns.map((column) => (
                    <div
                      key={column.key}
                      className={cn(
                        "truncate border-r border-border/70 px-2 last:border-r-0",
                        column.align === "right" && "text-right"
                      )}
                    >
                      {column.render(row)}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function OverviewLocationMap({
  rows,
  selectedId,
  trajectoryOn,
  onSelect,
}: {
  rows: CellebriteRecord[]
  selectedId: string | null
  trajectoryOn: boolean
  onSelect: (row: CellebriteRecord) => void
}) {
  const mapRef = useRef<MapRef | null>(null)
  const { styleUrl } = useMapTheme()
  const points = useMemo(() => locationPoints(rows), [rows])
  const geoJson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: points.map((point) => ({
        type: "Feature" as const,
        properties: {
          key: point.key,
          name: readText(point.row, ["name", "label", "location_type"], "Location"),
        },
        geometry: {
          type: "Point" as const,
          coordinates: [point.longitude, point.latitude],
        },
      })),
    }),
    [points]
  )
  const trajectoryGeoJson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: trajectoryOn && points.length > 1
        ? [{
            type: "Feature" as const,
            properties: {},
            geometry: {
              type: "LineString" as const,
              coordinates: points
                .slice()
                .sort((a, b) => String(a.timestamp ?? "").localeCompare(String(b.timestamp ?? "")))
                .map((point) => [point.longitude, point.latitude]),
            },
          }]
        : [],
    }),
    [points, trajectoryOn]
  )
  const center = points[0] ?? { longitude: -6.2603, latitude: 53.3498 }

  const fitPoints = useCallback(() => {
    if (!mapRef.current || points.length === 0) return
    if (points.length === 1) {
      mapRef.current.flyTo({ center: [points[0].longitude, points[0].latitude], zoom: 13, duration: 0 })
      return
    }
    const lngs = points.map((point) => point.longitude)
    const lats = points.map((point) => point.latitude)
    mapRef.current.fitBounds(
      [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ],
      { padding: 60, duration: 700 }
    )
  }, [points])

  useEffect(() => {
    const selected = points.find((point) => point.key === selectedId)
    if (!selected || !mapRef.current) return
    mapRef.current.flyTo({
      center: [selected.longitude, selected.latitude],
      zoom: Math.max(mapRef.current.getZoom(), 13),
      duration: 600,
    })
  }, [points, selectedId])

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const key = event.features?.[0]?.properties?.key
      if (!key) return
      const point = points.find((item) => item.key === key)
      if (point) onSelect(point.row)
    },
    [onSelect, points]
  )

  const handleMouseMove = useCallback((event: MapLayerMouseEvent) => {
    const map = mapRef.current?.getMap()
    if (map) map.getCanvas().style.cursor = event.features?.length ? "pointer" : ""
  }, [])

  const handleMouseLeave = useCallback(() => {
    const map = mapRef.current?.getMap()
    if (map) map.getCanvas().style.cursor = ""
  }, [])

  return (
    <div className="relative h-full min-h-0 bg-muted/30">
      {points.length === 0 && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80 text-sm text-muted-foreground">
          No geolocated locations on this device.
        </div>
      )}
      <MaplibreMap
        ref={mapRef}
        mapLib={maplibregl}
        mapStyle={styleUrl}
        initialViewState={{
          longitude: center.longitude,
          latitude: center.latitude,
          zoom: points.length ? 9 : 5,
        }}
        style={{ width: "100%", height: "100%" }}
        attributionControl={false}
        interactiveLayerIds={["overview-location-points"]}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onLoad={fitPoints}
      >
        <NavigationControl position="top-right" showCompass={false} visualizePitch={false} />
        {trajectoryOn && (
          <Source id="overview-location-trajectory" type="geojson" data={trajectoryGeoJson}>
            <Layer
              id="overview-location-trajectory-line"
              type="line"
              paint={{ "line-color": "#0891b2", "line-width": 3, "line-opacity": 0.75 }}
            />
          </Source>
        )}
        <Source id="overview-location-source" type="geojson" data={geoJson}>
          <Layer
            id="overview-location-points"
            type="circle"
            paint={{
              "circle-color": ["case", ["==", ["get", "key"], selectedId ?? ""], "#f59e0b", "#0891b2"],
              "circle-radius": ["case", ["==", ["get", "key"], selectedId ?? ""], 9, 6],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-opacity": 0.9,
            }}
          />
        </Source>
      </MaplibreMap>
    </div>
  )
}

function rowsForOverview(kind: OverviewKind, data: CellebriteRecord | undefined): CellebriteRecord[] {
  if (!data) return []
  const value = data.rows ?? data[kind]
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function overviewDetailColumns(
  kind: OverviewKind,
  caseId: string,
  report: PhoneReport,
  onFilterComms: (seed: CommsSeed) => void
): OverviewDetailColumn[] {
  if (kind === "contacts") {
    return [
      {
        key: "name",
        label: "Name",
        width: "minmax(180px,1fr)",
        getSortValue: (row) => readText(row, ["name", "display_name", "key"]),
        render: (row) => (
          <span className="flex items-center gap-1.5">
            {row.is_phone_owner ? (
              <Smartphone className="size-3.5 text-emerald-600" />
            ) : (
              <UserRound className="size-3.5 text-muted-foreground" />
            )}
            <span className="truncate">{readText(row, ["name", "display_name", "key"], "-")}</span>
          </span>
        ),
      },
      {
        key: "phone_numbers",
        label: "Phone numbers",
        width: "minmax(180px,1fr)",
        render: (row) => formatPhoneNumbers(row),
      },
      {
        key: "calls",
        label: "Calls",
        width: "90px",
        align: "right",
        getSortValue: (row) => readNumber(row, ["calls", "call_count"]),
        render: (row) => overviewCountWithIcon(row, ["calls", "call_count"], Phone, "text-emerald-700"),
      },
      {
        key: "messages",
        label: "Messages",
        width: "110px",
        align: "right",
        getSortValue: (row) => readNumber(row, ["messages", "message_count"]),
        render: (row) => overviewCountWithIcon(row, ["messages", "message_count"], MessageSquare, "text-blue-700"),
      },
      {
        key: "emails",
        label: "Emails",
        width: "90px",
        align: "right",
        getSortValue: (row) => readNumber(row, ["emails", "email_count"]),
        render: (row) => overviewCountWithIcon(row, ["emails", "email_count"], Mail, "text-amber-700"),
      },
      {
        key: "interactions",
        label: "Total",
        width: "90px",
        align: "right",
        getSortValue: (row) => readNumber(row, ["interactions", "total", "total_count"]),
        render: (row) => compactNumber(readNumber(row, ["interactions", "total", "total_count"])),
      },
      {
        key: "_filter",
        label: "",
        width: "48px",
        align: "right",
        sortable: false,
        render: (row) => (
          <OverviewFilterCommsButton
            caseId={caseId}
            report={report}
            personKeys={[readText(row, ["key", "person_key", "id"])]}
            type="all"
            label={readText(row, ["name", "display_name", "key"], "Contact")}
            onFilterComms={onFilterComms}
          />
        ),
      },
    ]
  }

  if (kind === "calls") {
    return [
      {
        key: "timestamp",
        label: "Time",
        width: "160px",
        render: (row) => compactDate(row.timestamp ?? row.datetime ?? row.time),
      },
      {
        key: "direction",
        label: "Direction",
        width: "140px",
        render: (row) => <CallDirectionCell row={row} />,
      },
      {
        key: "call_type",
        label: "Type",
        width: "120px",
        render: (row) => readText(row, ["call_type", "type"], "-"),
      },
      {
        key: "duration",
        label: "Duration",
        width: "110px",
        getSortValue: (row) => readNumber(row, ["duration", "duration_seconds"]),
        render: (row) => formatDuration(row.duration ?? row.duration_seconds),
      },
      {
        key: "from_name",
        label: "From",
        width: "minmax(140px,1fr)",
        render: (row) => readText(row, ["from_name", "from_key", "sender_name", "caller"], "-"),
      },
      {
        key: "to_name",
        label: "To",
        width: "minmax(140px,1fr)",
        render: (row) => readText(row, ["to_name", "to_key", "recipient_name", "callee"], "-"),
      },
      {
        key: "source_app",
        label: "Source app",
        width: "150px",
        render: (row) => readText(row, ["source_app", "app"], "-"),
      },
      {
        key: "_filter",
        label: "",
        width: "48px",
        align: "right",
        sortable: false,
        render: (row) => (
          <OverviewFilterCommsButton
            caseId={caseId}
            report={report}
            personKeys={[readText(row, ["from_key", "sender_key"]), readText(row, ["to_key", "recipient_key"])]}
            type="call"
            label={`${readText(row, ["from_name", "from_key"], "?")} - ${readText(row, ["to_name", "to_key"], "?")}`}
            onFilterComms={onFilterComms}
          />
        ),
      },
    ]
  }

  if (kind === "messages") {
    return [
      {
        key: "timestamp",
        label: "Time",
        width: "160px",
        render: (row) => compactDate(row.timestamp ?? row.datetime ?? row.time),
      },
      {
        key: "source_app",
        label: "App",
        width: "150px",
        render: (row) => readText(row, ["source_app", "app"], "-"),
      },
      {
        key: "sender_name",
        label: "Sender",
        width: "180px",
        render: (row) => readText(row, ["sender_name", "sender_key", "from_name"], "-"),
      },
      {
        key: "body_preview",
        label: "Body",
        width: "minmax(240px,1.5fr)",
        render: (row) => truncate(readText(row, ["body_preview", "body", "summary"], ""), 140),
      },
      {
        key: "attachment_count",
        label: "Attachments",
        width: "120px",
        align: "right",
        getSortValue: (row) => readNumber(row, ["attachment_count", "attachments_count"]),
        render: (row) => attachmentCount(row),
      },
      {
        key: "_filter",
        label: "",
        width: "48px",
        align: "right",
        sortable: false,
        render: (row) => (
          <OverviewFilterCommsButton
            caseId={caseId}
            report={report}
            personKeys={[readText(row, ["sender_key", "from_key"])]}
            type="message"
            label={readText(row, ["sender_name", "sender_key"], "Sender")}
            onFilterComms={onFilterComms}
          />
        ),
      },
    ]
  }

  if (kind === "emails") {
    return [
      {
        key: "direction",
        label: "",
        width: "60px",
        render: (row) => <EmailDirectionChip direction={readText(row, ["direction"])} />,
      },
      {
        key: "timestamp",
        label: "Time",
        width: "160px",
        render: (row) => compactDate(row.timestamp ?? row.datetime ?? row.time),
      },
      {
        key: "subject",
        label: "Subject",
        width: "minmax(240px,1.5fr)",
        render: (row) => readText(row, ["subject"], "(no subject)"),
      },
      {
        key: "from_name",
        label: "From",
        width: "200px",
        render: (row) => readText(row, ["from_name", "from_key", "sender_name"], "-"),
      },
      {
        key: "to_name",
        label: "To",
        width: "200px",
        render: (row) => emailRecipient(row),
      },
      {
        key: "folder",
        label: "Folder",
        width: "160px",
        render: (row) => folderCell(row),
      },
      {
        key: "attachment_count",
        label: "Attach.",
        width: "90px",
        align: "right",
        getSortValue: (row) => readNumber(row, ["attachment_count", "attachments_count"]),
        render: (row) => attachmentCount(row),
      },
      {
        key: "_filter",
        label: "",
        width: "48px",
        align: "right",
        sortable: false,
        render: (row) => (
          <OverviewFilterCommsButton
            caseId={caseId}
            report={report}
            personKeys={[readText(row, ["from_key", "sender_key"]), readText(row, ["to_key", "recipient_key"])]}
            type="email"
            label={`${readText(row, ["from_name", "from_key"], "?")} - ${readText(row, ["to_name", "to_key"], "?")}`}
            onFilterComms={onFilterComms}
          />
        ),
      },
    ]
  }

  return [
    {
      key: "timestamp",
      label: "Time",
      width: "160px",
      render: (row) => compactDate(row.timestamp ?? row.datetime ?? row.time),
    },
    {
      key: "name",
      label: "Name",
      width: "220px",
      render: (row) => readText(row, ["name", "label", "address"], "-"),
    },
    {
      key: "location_type",
      label: "Type / Source",
      width: "minmax(240px,1fr)",
      render: (row) => [readText(row, ["location_type", "type"]), readText(row, ["source_app", "app"])]
        .filter(Boolean)
        .join(" / ") || "-",
    },
    {
      key: "latitude",
      label: "Lat / Lon",
      width: "200px",
      render: (row) => coordinateCell(row),
    },
  ]
}

function OverviewFilterCommsButton({
  report,
  personKeys,
  type,
  label,
  onFilterComms,
}: {
  caseId: string
  report: PhoneReport
  personKeys: string[]
  type: CommsSeed["type"]
  label: string
  onFilterComms: (seed: CommsSeed) => void
}) {
  const cleanKeys = personKeys.filter(Boolean)
  if (!cleanKeys.length) return <span className="text-muted-foreground">-</span>
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      title="Filter communications"
      onClick={(event) => {
        event.stopPropagation()
        onFilterComms({
          id: `overview-filter-${report.report_key}-${cleanKeys.join("-")}-${type}`,
          reportKey: report.report_key,
          participantKeys: cleanKeys,
          type,
          label,
        })
      }}
    >
      <Filter className="size-3.5" />
    </Button>
  )
}

function overviewSelectionForRow(
  kind: OverviewKind,
  row: CellebriteRecord,
  report: PhoneReport
): RailSelection {
  if (kind === "contacts") {
    return {
      id: itemKey(row, "contact"),
      kind: "contact",
      title: readText(row, ["name", "display_name", "key"], "Contact"),
      payload: { ...row, report_key: report.report_key },
    }
  }
  if (kind === "messages" && readText(row, ["thread_id"])) {
    return {
      id: readText(row, ["thread_id"], itemKey(row, "thread")),
      kind: "thread",
      title: readText(row, ["thread_name", "source_app", "body_preview", "body"], "Conversation"),
      payload: {
        ...row,
        thread_type: "chat",
        report_key: report.report_key,
        anchor_key: readText(row, ["node_key", "key"]),
        message_id: itemKey(row, "message"),
      },
    }
  }
  if (kind === "emails" && readText(row, ["thread_id"])) {
    return {
      id: readText(row, ["thread_id"], itemKey(row, "thread")),
      kind: "thread",
      title: readText(row, ["subject", "thread_name"], "Email conversation"),
      payload: {
        ...row,
        thread_type: "emails",
        report_key: report.report_key,
        message_id: itemKey(row, "email"),
      },
    }
  }
  return {
    id: itemKey(row, kind),
    kind: kind === "locations" || kind === "calls" || kind === "emails" || kind === "messages" ? "event" : "report",
    title: readText(row, ["subject", "summary", "label", "name", "event_type", "type"], overviewKindMeta(kind).singular),
    payload: { ...row, report_key: report.report_key },
  }
}

function overviewKindMeta(kind: OverviewKind): { label: string; singular: string; icon: typeof Smartphone } {
  if (kind === "contacts") return { label: "Contacts", singular: "Contact", icon: UserRound }
  if (kind === "calls") return { label: "Calls", singular: "Call", icon: Phone }
  if (kind === "messages") return { label: "Messages", singular: "Message", icon: MessageSquare }
  if (kind === "locations") return { label: "Locations", singular: "Location", icon: MapPin }
  return { label: "Emails", singular: "Email", icon: Mail }
}

function overviewDefaultSort(kind: OverviewKind): OverviewSort {
  if (kind === "contacts") return { key: "interactions", dir: "desc" }
  return { key: "timestamp", dir: "desc" }
}

function overviewStatCount(report: PhoneReport, kind: OverviewKind): number {
  const keys: Record<OverviewKind, string[]> = {
    contacts: ["contacts", "contact_count"],
    calls: ["calls", "call_count"],
    messages: ["messages", "message_count"],
    locations: ["locations", "location_count"],
    emails: ["emails", "email_count"],
  }
  return readNumber(report.stats, keys[kind])
}

function overviewTotalComms(report: PhoneReport): number {
  return overviewStatCount(report, "calls") + overviewStatCount(report, "messages") + overviewStatCount(report, "emails")
}

function overviewToneClass(tone: OverviewKind | "total"): string {
  if (tone === "contacts") return "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200"
  if (tone === "calls") return "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200"
  if (tone === "messages") return "border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-900 dark:bg-violet-950/30 dark:text-violet-200"
  if (tone === "locations") return "border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-cyan-900 dark:bg-cyan-950/30 dark:text-cyan-200"
  if (tone === "emails") return "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200"
  return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
}

function reconciliationStatusClass(status: string): string {
  if (status === "nested") return "bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-200"
  if (status === "skipped" || status === "not_supported") return "bg-muted text-muted-foreground"
  if (status === "under") return "bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200"
  return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-200"
}

function sortOverviewRows(
  rows: CellebriteRecord[],
  columns: OverviewDetailColumn[],
  sort: OverviewSort
): CellebriteRecord[] {
  const column = columns.find((item) => item.key === sort.key)
  if (!column) return rows
  const factor = sort.dir === "asc" ? 1 : -1
  return rows.slice().sort((left, right) => {
    const leftValue = column.getSortValue?.(left) ?? left[column.key]
    const rightValue = column.getSortValue?.(right) ?? right[column.key]
    return compareOverviewValues(leftValue, rightValue) * factor
  })
}

function compareOverviewValues(left: unknown, right: unknown): number {
  if (left === null || left === undefined) return right === null || right === undefined ? 0 : 1
  if (right === null || right === undefined) return -1
  if (typeof left === "number" && typeof right === "number") return left - right
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" })
}

function formatPhoneNumbers(row: CellebriteRecord): string {
  const values = readList(row, ["phone_numbers", "phone_number", "phones"])
  if (!values.length) return "-"
  const extra = values.length > 2 ? ` +${values.length - 2}` : ""
  return `${values.slice(0, 2).join(", ")}${extra}`
}

function overviewCountWithIcon(
  row: CellebriteRecord,
  keys: string[],
  Icon: typeof Smartphone,
  color: string
): ReactNode {
  const value = readNumber(row, keys)
  if (value <= 0) return "-"
  return (
    <span className={cn("inline-flex items-center justify-end gap-1", color)}>
      <Icon className="size-3.5" />
      {compactNumber(value)}
    </span>
  )
}

function CallDirectionCell({ row }: { row: CellebriteRecord }) {
  const direction = readText(row, ["direction"])
  const callType = readText(row, ["call_type"])
  return (
    <span className="flex items-center gap-1.5">
      {callIconElement(direction, callType)}
      <span>{readText(row, ["direction"], "-")}</span>
      {Boolean(row.video_call) && <Video className="size-3 text-muted-foreground" />}
    </span>
  )
}

function callIconElement(direction: string, callType: string): ReactNode {
  const text = `${direction} ${callType}`.toLowerCase()
  if (text.includes("miss")) return <PhoneMissed className="size-3.5 text-red-600" />
  if (text.includes("incoming")) return <PhoneIncoming className="size-3.5 text-emerald-600" />
  if (text.includes("outgoing")) return <PhoneOutgoing className="size-3.5 text-emerald-600" />
  return <Phone className="size-3.5 text-emerald-600" />
}

function EmailDirectionChip({ direction }: { direction: string }) {
  const incoming = direction.toLowerCase() === "incoming"
  const Arrow = incoming ? ArrowDownLeft : ArrowUpRight
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-[10px] font-semibold uppercase", incoming ? "text-blue-700" : "text-emerald-700")}>
      <Arrow className="size-3" />
      {incoming ? "In" : "Out"}
    </span>
  )
}

function attachmentCount(row: CellebriteRecord): ReactNode {
  const count = readNumber(row, ["attachment_count", "attachments_count"])
  if (count <= 0) return "-"
  return (
    <span className="inline-flex items-center justify-end gap-1 text-amber-700">
      <Paperclip className="size-3.5" />
      {compactNumber(count)}
    </span>
  )
}

function folderCell(row: CellebriteRecord): ReactNode {
  const folder = readText(row, ["folder"])
  if (!folder) return "-"
  return (
    <span className="flex items-center gap-1">
      <Folder className="size-3 text-muted-foreground" />
      <span className="truncate">{folder}</span>
    </span>
  )
}

function emailRecipient(row: CellebriteRecord): string {
  const main = readText(row, ["to_name", "to_key", "recipient_name", "recipient_key"])
  if (!main) return "-"
  const more = readNumber(row, ["to_count"])
  return more > 1 ? `${main} +${more - 1}` : main
}

function coordinateCell(row: CellebriteRecord): ReactNode {
  const latitude = toFiniteNumber(row.latitude ?? row.lat)
  const longitude = toFiniteNumber(row.longitude ?? row.lng ?? row.lon)
  if (latitude === null || longitude === null) return "-"
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[10px]">
      <MapPin className="size-3 text-cyan-600" />
      {latitude.toFixed(4)}, {longitude.toFixed(4)}
    </span>
  )
}

function formatDuration(value: unknown): string {
  const seconds = toFiniteNumber(value)
  if (seconds === null) return asText(value, "-")
  const wholeSeconds = Math.max(0, Math.round(seconds))
  const hours = Math.floor(wholeSeconds / 3600)
  const minutes = Math.floor((wholeSeconds % 3600) / 60)
  const remainingSeconds = wholeSeconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${remainingSeconds}s`
  if (minutes > 0) return `${minutes}m ${remainingSeconds}s`
  return `${remainingSeconds}s`
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function locationPoints(rows: CellebriteRecord[]) {
  return rows.flatMap((row, index) => {
    const latitude = toFiniteNumber(row.latitude ?? row.lat)
    const longitude = toFiniteNumber(row.longitude ?? row.lng ?? row.lon)
    if (latitude === null || longitude === null) return []
    return [{
      key: itemKey(row, `location-${index}`),
      latitude,
      longitude,
      timestamp: row.timestamp ?? row.datetime ?? row.time,
      row,
    }]
  })
}
