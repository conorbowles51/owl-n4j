import { Trash2, GitMerge, Pencil, X, Star, StarOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { MAX_MERGE_ENTITIES } from "@/features/graph/lib/merge-limit"

interface BulkActionsBarProps {
  count: number
  onMerge: () => void
  onDelete: () => void
  onBulkEdit: () => void
  onClear: () => void
  significantMode?: boolean
  significantActionCount?: number
  onAddToSignificant?: () => void
  onRemoveFromSignificant?: () => void
  significantPending?: boolean
}

export function BulkActionsBar({
  count,
  onMerge,
  onDelete,
  onBulkEdit,
  onClear,
  significantMode = false,
  significantActionCount = 0,
  onAddToSignificant,
  onRemoveFromSignificant,
  significantPending = false,
}: BulkActionsBarProps) {
  if (count === 0) return null

  return (
    <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-1.5 animate-in slide-in-from-top-1 duration-200">
      <Badge variant="secondary" className="font-medium">
        {count} selected
      </Badge>

      <div className="flex items-center gap-1">
        {significantMode && onRemoveFromSignificant ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-amber-700 dark:text-amber-300"
            disabled={significantPending || significantActionCount === 0}
            onClick={onRemoveFromSignificant}
          >
            <StarOff className="size-3.5" />
            Remove from Significant
          </Button>
        ) : onAddToSignificant && significantActionCount > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-amber-700 dark:text-amber-300"
            disabled={significantPending}
            onClick={onAddToSignificant}
          >
            <Star className="size-3.5" />
            Add {significantActionCount.toLocaleString()} to Significant
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          disabled={count < 2}
          onClick={onMerge}
          title={
            count < 2
              ? "Select 2 or more entities to merge"
              : count > MAX_MERGE_ENTITIES
                ? `One merge takes up to ${MAX_MERGE_ENTITIES}: the first ${MAX_MERGE_ENTITIES} are merged, ${count - MAX_MERGE_ENTITIES} left out`
                : `Merge ${count} entities in one step`
          }
        >
          <GitMerge className="size-3.5" />
          {count >= 2 ? `Merge ${Math.min(count, MAX_MERGE_ENTITIES)}` : "Merge"}
        </Button>
        {count > MAX_MERGE_ENTITIES && (
          <span className="text-[11px] text-amber-700 dark:text-amber-300" data-testid="merge-limit">
            up to {MAX_MERGE_ENTITIES} per merge; {count - MAX_MERGE_ENTITIES} left out
          </span>
        )}
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
