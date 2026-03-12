import { Trash2, GitMerge, Pencil, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface BulkActionsBarProps {
  count: number
  onMerge: () => void
  onDelete: () => void
  onBulkEdit: () => void
  onClear: () => void
}

export function BulkActionsBar({
  count,
  onMerge,
  onDelete,
  onBulkEdit,
  onClear,
}: BulkActionsBarProps) {
  if (count === 0) return null

  return (
    <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-1.5 animate-in slide-in-from-top-1 duration-200">
      <Badge variant="secondary" className="font-medium">
        {count} selected
      </Badge>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          disabled={count !== 2}
          onClick={onMerge}
          title={count !== 2 ? "Select exactly 2 entities to merge" : "Merge entities"}
        >
          <GitMerge className="size-3.5" />
          Merge
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={onBulkEdit}
        >
          <Pencil className="size-3.5" />
          Bulk Edit
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-destructive hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="size-3.5" />
          Delete
        </Button>
      </div>

      <div className="flex-1" />

      <Button variant="ghost" size="icon-sm" onClick={onClear} title="Clear selection">
        <X className="size-3.5" />
      </Button>
    </div>
  )
}
