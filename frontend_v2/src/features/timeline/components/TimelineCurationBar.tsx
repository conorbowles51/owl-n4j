import { Download, Plus, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { TimelineView } from "../api"

interface TimelineCurationBarProps {
  selectedCount: number
  views: TimelineView[]
  activeView: TimelineView | null
  targetViewId: string | null
  onTargetViewChange: (viewId: string) => void
  onCreateFromSelection: () => void
  onAddToView: () => void
  onRemoveFromView: () => void
  onExportSelected: () => void
  onClear: () => void
}

export function TimelineCurationBar({
  selectedCount,
  views,
  activeView,
  targetViewId,
  onTargetViewChange,
  onCreateFromSelection,
  onAddToView,
  onRemoveFromView,
  onExportSelected,
  onClear,
}: TimelineCurationBarProps) {
  const hasSelection = selectedCount > 0

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-3 py-2">
      <span className="mr-1 text-xs font-semibold text-foreground">
        {selectedCount} selected
      </span>

      <Button variant="outline" size="sm" onClick={onCreateFromSelection} disabled={!hasSelection}>
        <Plus className="size-3.5" />
        New view
      </Button>

      {views.length > 0 && (
        <>
          <Select
            value={targetViewId ?? views[0]?.id}
            onValueChange={onTargetViewChange}
          >
            <SelectTrigger className="h-7 w-[180px] bg-background text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {views.map((view) => (
                <SelectItem key={view.id} value={view.id}>
                  {view.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={onAddToView} disabled={!hasSelection || !targetViewId}>
            Add
          </Button>
        </>
      )}

      {activeView && (
        <Button variant="outline" size="sm" onClick={onRemoveFromView} disabled={!hasSelection}>
          <Trash2 className="size-3.5" />
          Remove
        </Button>
      )}

      <Button variant="outline" size="sm" onClick={onExportSelected} disabled={!hasSelection}>
        <Download className="size-3.5" />
        Export selected
      </Button>

      <Button variant="ghost" size="sm" onClick={onClear} disabled={!hasSelection}>
        <X className="size-3.5" />
        Clear
      </Button>
    </div>
  )
}
