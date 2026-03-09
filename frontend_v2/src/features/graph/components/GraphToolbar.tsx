import {
  Search,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Plus,
  GitBranch,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useGraphStore } from "@/stores/graph.store"

interface GraphToolbarProps {
  caseId: string
}

export function GraphToolbar({ caseId: _caseId }: GraphToolbarProps) {
  const { searchTerm, setSearchTerm, viewSettings, setViewSetting } =
    useGraphStore()

  return (
    <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
      <div className="relative flex-1 max-w-xs">
        <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search graph..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="h-7 pl-8 text-xs"
        />
      </div>

      <div className="flex items-center gap-1 border-l border-border pl-2">
        <Button variant="ghost" size="icon-sm">
          <ZoomIn className="size-3.5" />
        </Button>
        <Button variant="ghost" size="icon-sm">
          <ZoomOut className="size-3.5" />
        </Button>
        <Button variant="ghost" size="icon-sm">
          <Maximize2 className="size-3.5" />
        </Button>
      </div>

      <div className="flex items-center gap-1 border-l border-border pl-2">
        <select
          value={viewSettings.layout}
          onChange={(e) =>
            setViewSetting(
              "layout",
              e.target.value as typeof viewSettings.layout
            )
          }
          className="h-7 rounded-md border border-input bg-transparent px-2 text-xs text-foreground"
        >
          <option value="force">Force</option>
          <option value="hierarchical">Hierarchical</option>
          <option value="radial">Radial</option>
          <option value="circular">Circular</option>
        </select>
      </div>

      <div className="flex items-center gap-1 border-l border-border pl-2">
        <Button variant="ghost" size="sm" className="text-xs">
          <Plus className="size-3.5" />
          Add Node
        </Button>
        <Button variant="ghost" size="sm" className="text-xs">
          <GitBranch className="size-3.5" />
          Relationship
        </Button>
      </div>
    </div>
  )
}
