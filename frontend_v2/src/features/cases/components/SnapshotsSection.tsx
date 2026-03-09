import { useState, useMemo } from "react"
import {
  Camera,
  Trash2,
  Download,
  ChevronDown,
  ChevronRight,
  Clock,
  Search,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useSnapshots, useDeleteSnapshot } from "../hooks/use-snapshots"
import type { Snapshot } from "../snapshots-api"

interface SnapshotsSectionProps {
  caseId: string
}

const PAGE_SIZE = 10

export function SnapshotsSection({ caseId }: SnapshotsSectionProps) {
  const { data: snapshots, isLoading } = useSnapshots()
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
        {caseSnapshots.length > 0 && (
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
            search ? "No matches" : "Save a snapshot from the graph workspace"
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
}: {
  snapshot: Snapshot
  isLatest: boolean
  isExpanded: boolean
  onToggle: () => void
  onDelete: () => void
  isDeleting: boolean
}) {
  return (
    <div className="rounded-md border border-border bg-card">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-accent/30"
      >
        {isExpanded ? (
          <ChevronDown className="size-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-xs font-medium">{snapshot.name}</p>
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
        <div className="border-t border-border px-3 py-2 text-xs">
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
          <div className="mt-2 flex gap-2">
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
          </div>
        </div>
      )}
    </div>
  )
}
