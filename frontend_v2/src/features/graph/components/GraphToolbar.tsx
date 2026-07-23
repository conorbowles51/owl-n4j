import { useEffect, useRef } from "react"
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
  X,
  HelpCircle,
  Box,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useGraphStore } from "@/stores/graph.store"
import type { ForceGraphMethods } from "react-force-graph-2d"
import type { ForceGraphMethods as ForceGraph3DMethods } from "react-force-graph-3d"
import type { CaseLayer } from "@/features/significant/types"

interface GraphToolbarProps {
  caseId: string
  graphRef?: React.MutableRefObject<ForceGraphMethods | undefined>
  graph3dRef?: React.MutableRefObject<ForceGraph3DMethods | undefined>
  onOpenAddNode?: () => void
  onOpenCreateRelationship?: () => void
  onOpenForceControls?: () => void
  onOpenAnalysis?: () => void
  onOpenSimilarEntities?: () => void
  onOpenRecycleBin?: () => void
  onOpenCypher?: () => void
  scope: CaseLayer
  filteredNodes: number
  totalNodes: number
}

export function GraphToolbar({
  graphRef,
  graph3dRef,
  onOpenAddNode,
  onOpenCreateRelationship,
  onOpenForceControls,
  onOpenAnalysis,
  onOpenSimilarEntities,
  onOpenRecycleBin,
  onOpenCypher,
  scope,
  filteredNodes,
  totalNodes,
}: GraphToolbarProps) {
  const {
    searchMode,
    searchDraft,
    appliedSearchQuery,
    setSearchMode,
    setSearchDraft,
    applySearch,
    clearSearch,
    selectionMode,
    setSelectionMode,
    hiddenNodeKeys,
    unhideAll,
    subgraphNodeKeys,
    spotlightVisible,
    toggleSpotlight,
    graphDimension,
    toggleGraphDimension,
  } = useGraphStore()
  const searchInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (searchMode !== "filter") return
    if (!searchDraft.trim()) {
      applySearch("")
      return
    }
    const timeout = window.setTimeout(() => applySearch(), 300)
    return () => window.clearTimeout(timeout)
  }, [applySearch, searchDraft, searchMode])

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault()
        searchInputRef.current?.focus()
        searchInputRef.current?.select()
      }
    }
    window.addEventListener("keydown", focusSearch)
    return () => window.removeEventListener("keydown", focusSearch)
  }, [])

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && searchMode === "search") {
      event.preventDefault()
      applySearch()
    } else if (event.key === "Escape" && (searchDraft || appliedSearchQuery)) {
      event.preventDefault()
      clearSearch()
    }
  }

  const handleModeChange = (mode: "filter" | "search") => {
    setSearchMode(mode)
    if (mode === "filter") applySearch()
  }

  const zoomIn = () => {
    if (graphDimension === "3d") {
      const fg = graph3dRef?.current
      if (!fg) return
      const { x, y, z } = fg.camera().position
      fg.cameraPosition({ x: x * 0.75, y: y * 0.75, z: z * 0.75 }, undefined, 400)
      return
    }
    const fg = graphRef?.current
    if (!fg) return
    const z = fg.zoom()
    if (z) fg.zoom(z * 1.5, 400)
  }

  const zoomOut = () => {
    if (graphDimension === "3d") {
      const fg = graph3dRef?.current
      if (!fg) return
      const { x, y, z } = fg.camera().position
      fg.cameraPosition({ x: x * 1.35, y: y * 1.35, z: z * 1.35 }, undefined, 400)
      return
    }
    const fg = graphRef?.current
    if (!fg) return
    const z = fg.zoom()
    if (z) fg.zoom(z / 1.5, 400)
  }

  const zoomToFit = () => {
    if (graphDimension === "3d") {
      graph3dRef?.current?.zoomToFit(400, 50)
    } else {
      graphRef?.current?.zoomToFit(400, 50)
    }
  }

  return (
    <div className="flex items-center gap-2 overflow-x-auto border-b border-border bg-card/95 px-3 py-1.5 backdrop-blur-sm">
      {/* Search */}
      <div className="flex min-w-[340px] max-w-xl flex-1 items-center gap-1.5">
        <div className="relative min-w-[160px] flex-1">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={searchInputRef}
            aria-label={`${searchMode === "filter" ? "Filter" : "Search"} graph entities`}
            placeholder={searchMode === "filter" ? "Filter graph..." : "Fuzzy search graph..."}
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="h-7 pl-8 pr-7 text-xs"
          />
          {searchDraft ? (
            <button
              type="button"
              aria-label="Clear graph search"
              onClick={() => {
                clearSearch()
                searchInputRef.current?.focus()
              }}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>
        <select
          aria-label="Graph search mode"
          value={searchMode}
          onChange={(event) => handleModeChange(event.target.value as "filter" | "search")}
          className="h-7 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="filter">Filter</option>
          <option value="search">Search</option>
        </select>
        {searchMode === "search" ? (
          <Button size="sm" className="h-7 text-xs" onClick={() => applySearch()}>
            Search
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Filter syntax help">
                <HelpCircle className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Use AND, OR, NOT, -term, quotes, * and ?</TooltipContent>
          </Tooltip>
        )}
        <span className="whitespace-nowrap text-[10px] text-muted-foreground" aria-live="polite">
          {filteredNodes.toLocaleString()} / {totalNodes.toLocaleString()}
        </span>
      </div>

      {/* Zoom controls */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={zoomIn} aria-label="Zoom in">
              <ZoomIn className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom In</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={zoomOut} aria-label="Zoom out">
              <ZoomOut className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom Out</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={zoomToFit} aria-label="Fit graph to view">
              <Maximize2 className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Fit to View</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={graphDimension === "3d" ? "secondary" : "ghost"}
              size="icon-sm"
              onClick={toggleGraphDimension}
              aria-label={`Switch to ${graphDimension === "2d" ? "3D" : "2D"} graph view`}
              aria-pressed={graphDimension === "3d"}
            >
              <Box className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Switch main and Spotlight graphs to {graphDimension === "2d" ? "3D" : "2D"}
          </TooltipContent>
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
              disabled={graphDimension === "3d"}
              aria-label="Drag select"
            >
              <BoxSelect className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Drag Select</TooltipContent>
        </Tooltip>
      </div>

      {/* Node actions */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        {scope === "all" && (
          <Button variant="ghost" size="sm" className="text-xs" onClick={onOpenAddNode}>
            <Plus className="size-3.5" />
            Add Node
          </Button>
        )}
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
        {scope === "all" && (
          <>
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
          </>
        )}
      </div>

      {/* Spotlight / Recycle */}
      <div className="flex items-center gap-0.5 border-l border-border pl-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={spotlightVisible && subgraphNodeKeys.size > 0 ? "secondary" : "ghost"}
              size="icon-sm"
              className="relative"
              onClick={toggleSpotlight}
            >
              <Focus className="size-3.5" />
              {subgraphNodeKeys.size > 0 && (
                <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-semibold text-white">
                  {subgraphNodeKeys.size}
                </span>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Spotlight Graph</TooltipContent>
        </Tooltip>
        {scope === "all" && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" onClick={onOpenRecycleBin}>
                <Trash2 className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Recycle Bin</TooltipContent>
          </Tooltip>
        )}
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
