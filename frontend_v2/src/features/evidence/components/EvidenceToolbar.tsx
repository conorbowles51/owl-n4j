import { Search, X, Play, Trash2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useEvidenceStore } from "../evidence.store"

const STATUS_FILTERS = [
  { value: "all" as const, label: "All" },
  { value: "unprocessed" as const, label: "Unprocessed" },
  { value: "processing" as const, label: "Processing" },
  { value: "processed" as const, label: "Processed" },
  { value: "failed" as const, label: "Failed" },
]

interface EvidenceToolbarProps {
  onProcess?: () => void
  onDelete?: () => void
  processPending?: boolean
}

export function EvidenceToolbar({ onProcess, onDelete, processPending }: EvidenceToolbarProps) {
  const {
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    selectedFileIds,
    clearSelection,
  } = useEvidenceStore()

  const selectionCount = selectedFileIds.size

  return (
    <div className="flex flex-col gap-2 border-b border-border px-6 py-2">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search files..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-8 h-8"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
                statusFilter === f.value
                  ? "bg-amber-500/15 text-amber-500"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {selectionCount > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-1.5">
          <Badge variant="info" className="text-xs">
            {selectionCount} selected
          </Badge>
          <Button
            variant="primary"
            size="sm"
            onClick={onProcess}
            disabled={processPending}
            className="h-7 text-xs"
          >
            <Play className="size-3" />
            Process
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={onDelete}
            className="h-7 text-xs"
          >
            <Trash2 className="size-3" />
            Delete
          </Button>
          <button
            onClick={clearSelection}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Clear selection
          </button>
        </div>
      )}
    </div>
  )
}
