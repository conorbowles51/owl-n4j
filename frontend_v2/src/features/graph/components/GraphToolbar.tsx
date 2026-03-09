import {
  Search,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Plus,
  GitBranch,
  MousePointer,
  BoxSelect,
  Settings2,
  BarChart3,
  Users,
  Trash2,
  Terminal,
  Focus,
  EyeOff,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useGraphStore } from "@/stores/graph.store"
import type { ForceGraphMethods } from "react-force-graph-2d"

interface GraphToolbarProps {
  caseId: string
  graphRef?: React.MutableRefObject<ForceGraphMethods | undefined>
  onOpenAddNode?: () => void
  onOpenCreateRelationship?: () => void
  onOpenForceControls?: () => void
  onOpenAnalysis?: () => void
  onOpenSimilarEntities?: () => void
  onOpenRecycleBin?: () => void
  onOpenCypher?: () => void
}

export function GraphToolbar({
  graphRef,
  onOpenAddNode,
  onOpenCreateRelationship,
  onOpenForceControls,
  onOpenAnalysis,
  onOpenSimilarEntities,
  onOpenRecycleBin,
  onOpenCypher,
}: GraphToolbarProps) {
  const {
    searchTerm,
    setSearchTerm,
    selectionMode,
    setSelectionMode,
    hiddenNodeKeys,
    unhideAll,
    subgraphNodeKeys,
    spotlightVisible,
    toggleSpotlight,
  } = useGraphStore()

  const zoomIn = () => {
    const fg = graphRef?.current
    if (!fg) return
    const z = (fg as any).zoom?.()
    if (z) fg.zoom(z * 1.5, 400)
  }

  const zoomOut = () => {
    const fg = graphRef?.current
    if (!fg) return
    const z = (fg as any).zoom?.()
    if (z) fg.zoom(z / 1.5, 400)
  }

  const zoomToFit = () => {
    graphRef?.current?.zoomToFit(400, 50)
  }

  return (
    <div className="flex items-center gap-2 border-b border-border px-3 py-1.5 overflow-x-auto">
      {/* Search */}
      <div className="relative min-w-[160px] max-w-xs flex-1">
        <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search graph..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="h-7 pl-8 text-xs"
        />
      </div>

      {/* Zoom controls */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={zoomIn}>
              <ZoomIn className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom In</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={zoomOut}>
              <ZoomOut className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom Out</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={zoomToFit}>
              <Maximize2 className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Fit to View</TooltipContent>
        </Tooltip>
      </div>

      {/* Selection mode */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={selectionMode === "click" ? "secondary" : "ghost"}
              size="icon-sm"
              onClick={() => setSelectionMode("click")}
            >
              <MousePointer className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Click Select</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={selectionMode === "drag" ? "secondary" : "ghost"}
              size="icon-sm"
              onClick={() => setSelectionMode("drag")}
            >
              <BoxSelect className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Drag Select</TooltipContent>
        </Tooltip>
      </div>

      {/* Node actions */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onOpenAddNode}>
          <Plus className="size-3.5" />
          Add Node
        </Button>
        <Button variant="ghost" size="sm" className="text-xs" onClick={onOpenCreateRelationship}>
          <GitBranch className="size-3.5" />
          Relationship
        </Button>
      </div>

      {/* Tools */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onOpenForceControls}>
              <Settings2 className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Force Controls</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onOpenAnalysis}>
              <BarChart3 className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Graph Analysis</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onOpenSimilarEntities}>
              <Users className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Find Similar Entities</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onOpenCypher}>
              <Terminal className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Cypher Query</TooltipContent>
        </Tooltip>
      </div>

      {/* Spotlight / Recycle */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={spotlightVisible && subgraphNodeKeys.size > 0 ? "secondary" : "ghost"}
              size="icon-sm"
              onClick={toggleSpotlight}
            >
              <Focus className="size-3.5" />
              {subgraphNodeKeys.size > 0 && (
                <Badge variant="amber" className="ml-0.5 px-1 text-[9px]">
                  {subgraphNodeKeys.size}
                </Badge>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Spotlight Graph</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={onOpenRecycleBin}>
              <Trash2 className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Recycle Bin</TooltipContent>
        </Tooltip>
        {hiddenNodeKeys.size > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="sm" className="text-xs" onClick={unhideAll}>
                <EyeOff className="size-3.5" />
                {hiddenNodeKeys.size} hidden
              </Button>
            </TooltipTrigger>
            <TooltipContent>Unhide all nodes</TooltipContent>
          </Tooltip>
        )}
      </div>
    </div>
  )
}
