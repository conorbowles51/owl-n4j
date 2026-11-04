import { useState, useMemo } from "react"
import { toast } from "sonner"
import {
  Camera,
  Trash2,
  ChevronDown,
  ChevronRight,
  Clock,
  Search,
  FileDown,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useSnapshots, useDeleteSnapshot } from "../hooks/use-snapshots"
import { PRIVILEGE_MARKING_LABELS, snapshotsAPI, type PrivilegeMarking, type Snapshot } from "../snapshots-api"

interface SnapshotsSectionProps {
  caseId: string
  canEdit?: boolean
}

const PAGE_SIZE = 10

export function SnapshotsSection({ caseId, canEdit = true }: SnapshotsSectionProps) {
  const { data: snapshots, isLoading } = useSnapshots(caseId)
  const deleteMutation = useDeleteSnapshot()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)

  const caseSnapshots = useMemo(
    () =>
      (snapshots ?? [])
        .filter((s) => s.case_id === caseId)
        .filter(
          (s) =>
            !search ||
            s.name.toLowerCase().includes(search.toLowerCase()) ||
            s.notes?.toLowerCase().includes(search.toLowerCase())
        )
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ),
    [snapshots, caseId, search]
  )

  const totalPages = Math.ceil(caseSnapshots.length / PAGE_SIZE)
  const paged = caseSnapshots.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const handleDeleteAll = () => {
    caseSnapshots.forEach((s) => deleteMutation.mutate(s.id))
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <LoadingSpinner size="sm" />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Search + actions */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search snapshots..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
            className="h-7 pl-7 text-xs"
          />
        </div>
        {canEdit && caseSnapshots.length > 0 && (
          <Button
            variant="danger"
            size="sm"
            className="h-7 text-xs"
            onClick={handleDeleteAll}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="size-3" />
            Delete All
          </Button>
        )}
      </div>

      {paged.length === 0 ? (
        <EmptyState
          icon={Camera}
          title="No snapshots"
          description={
            search ? "No matches" : "Save one from the Graph page with Save snapshot in its toolbar"
          }
          className="py-4"
        />
      ) : (
        <div className="space-y-1">
          {paged.map((snapshot, idx) => (
            <SnapshotRow
              key={snapshot.id}
              snapshot={snapshot}
              isLatest={page === 0 && idx === 0 && !search}
              isExpanded={expandedId === snapshot.id}
              onToggle={() =>
                setExpandedId(
                  expandedId === snapshot.id ? null : snapshot.id
                )
              }
              onDelete={() => deleteMutation.mutate(snapshot.id)}
              isDeleting={deleteMutation.isPending}
              canEdit={canEdit}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
          <span>
            {caseSnapshots.length} snapshot
            {caseSnapshots.length !== 1 ? "s" : ""}
          </span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Prev
            </Button>
            <span className="flex items-center px-1">
              {page + 1}/{totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function SnapshotRow({
  snapshot,
  isLatest,
  isExpanded,
  onToggle,
  onDelete,
  isDeleting,
  canEdit,
}: {
  snapshot: Snapshot
  isLatest: boolean
  isExpanded: boolean
  onToggle: () => void
  onDelete: () => void
  isDeleting: boolean
  canEdit: boolean
}) {
  return (
    <div className="border-b border-border bg-transparent last:border-b-0">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-card"
      >
        {isExpanded ? (
          <ChevronDown className="size-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="font-display truncate text-xs font-semibold">{snapshot.name}</p>
            {isLatest && (
              <Badge variant="amber" className="text-[9px]">
                Latest
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <Clock className="size-2.5" />
            {new Date(snapshot.created_at).toLocaleString()}
            <Badge variant="slate" className="text-[9px]">
              {snapshot.node_count} nodes
            </Badge>
            <Badge variant="slate" className="text-[9px]">
              {snapshot.link_count} links
            </Badge>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="ml-8 border-l-2 border-brand-400 bg-card px-4 py-3 text-xs">
          {snapshot.ai_overview && (
            <div className="mb-2">
              <p className="mb-0.5 font-medium text-muted-foreground">
                AI Overview
              </p>
              <p className="text-foreground">{snapshot.ai_overview}</p>
            </div>
          )}
          {snapshot.notes && (
            <p className="mb-2 text-muted-foreground">{snapshot.notes}</p>
          )}
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            {snapshot.timeline_count !== undefined && (
              <span>{snapshot.timeline_count} timeline events</span>
            )}
          </div>
          <SnapshotReportExport snapshot={snapshot} />
          {canEdit && <div className="mt-2 flex gap-2">
            <Button
              variant="danger"
              size="sm"
              className="h-6 text-xs"
              onClick={(e) => {
                e.stopPropagation()
                onDelete()
              }}
              disabled={isDeleting}
            >
              <Trash2 className="size-3" />
              Delete
            </Button>
          </div>}
        </div>
      )}
    </div>
  )
}

function SnapshotReportExport({ snapshot }: { snapshot: Snapshot }) {
  const [marking, setMarking] = useState<PrivilegeMarking>("unmarked")
  const [busy, setBusy] = useState(false)
  const exportReport = async () => {
    setBusy(true)
    try {
      const { blob, filename } = await snapshotsAPI.report(snapshot.id, marking)
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = filename
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      toast.success(`Report downloaded: ${filename}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Report not produced")
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
        Marking
        <select
          aria-label="Report privilege marking"
          className="rounded border border-border bg-background px-1 py-0.5 text-[11px] text-foreground"
          value={marking}
          disabled={busy}
          onChange={(e) => setMarking(e.target.value as PrivilegeMarking)}
        >
          {(Object.keys(PRIVILEGE_MARKING_LABELS) as PrivilegeMarking[]).map((value) => (
            <option key={value} value={value}>{PRIVILEGE_MARKING_LABELS[value]}</option>
          ))}
        </select>
      </label>
      <Button variant="secondary" size="sm" className="h-6 text-xs" onClick={exportReport} disabled={busy}>
        <FileDown className="size-3" />
        {busy ? "Preparing report…" : "Export report (PDF)"}
      </Button>
      <span className="text-[10px] text-muted-foreground">Marking is your choice, not a legal privilege determination.</span>
    </div>
  )
}
