import { lazy, Suspense, useRef, useState, useCallback, useMemo, useEffect } from "react"
import { useLocation, useParams } from "react-router-dom"
import type { ForceGraphMethods } from "react-force-graph-2d"
import type { ForceGraphMethods as ForceGraph3DMethods } from "react-force-graph-3d"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useGraphData } from "../hooks/use-graph-data"
import { useGraphSearch } from "../hooks/use-graph-search"
import { useGraphStore } from "@/stores/graph.store"
import { useQueryClient } from "@tanstack/react-query"
import { GraphCanvas } from "./GraphCanvas"
import { GraphToolbar } from "./GraphToolbar"
import { GraphLegend } from "./GraphLegend"
import { GraphContextMenu } from "./GraphContextMenu"
import { GraphSidePanelRail, GraphSidePanelContent } from "./GraphSidePanel"
import { AddNodeDialog } from "./AddNodeDialog"
import { EditNodeDialog } from "./EditNodeDialog"
import { CreateRelationshipDialog } from "./CreateRelationshipDialog"
import { MergeEntitiesDialog } from "./MergeEntitiesDialog"
import { useMergeTracker } from "../hooks/use-merge-tracker"
import { ExpandGraphDialog } from "./ExpandGraphDialog"
import { EntityComparisonDialog } from "./EntityComparisonDialog"
import { LoadProgress } from "@/features/financial/components/LoadProgress"
import type { PageWork } from "@/features/financial/lib/load-progress"
import { EmptyState } from "@/components/ui/empty-state"
import { Network } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { graphAPI } from "../api"
import { useUIStore } from "@/stores/ui.store"
import { SubgraphView } from "./SubgraphView"
import type { NodeDetail } from "@/types/graph.types"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"
import { SignificantEmptyState } from "@/features/significant/components/SignificantEmptyState"

const GraphCanvas3D = lazy(() =>
  import("./GraphCanvas3D").then((module) => ({ default: module.GraphCanvas3D }))
)

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function GraphPage() {
  const { id: caseId } = useParams()
  const location = useLocation()
  const queryClient = useQueryClient()
  const graphRef = useRef<ForceGraphMethods | undefined>(undefined)
  const graph3dRef = useRef<ForceGraph3DMethods | undefined>(undefined)
  const caseLayer = useCaseLayer(caseId)

  /* ---- Data fetching ---- */
  // When this case's graph was opened (before its read starts): one loading panel from the read to the end of
  // arranging a large graph, though it is shown in two places.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const openedAt = useMemo(() => performance.now(), [caseId])
  const [layoutWork, setLayoutWork] = useState<PageWork | null>(null)
  const { data: graphData, isLoading } = useGraphData(caseId, { phoneCap: true })
  const { filteredData, filteredNodes, totalNodes } = useGraphSearch(graphData)

  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const clearSearch = useGraphStore((s) => s.clearSearch)
  const setSelectedEntityTypes = useGraphStore((s) => s.setSelectedEntityTypes)
  const graphDimension = useGraphStore((s) => s.graphDimension)
  const hasSelection = selectedNodeKeys.size > 0

  useEffect(() => {
    clearSearch()
    setSelectedEntityTypes(null)
  }, [caseId, clearSearch, setSelectedEntityTypes])

  /* ---- Spotlight state ---- */
  const spotlightVisible = useGraphStore((s) => s.spotlightVisible)
  const subgraphNodeKeys = useGraphStore((s) => s.subgraphNodeKeys)
  const clearSubgraph = useGraphStore((s) => s.clearSubgraph)
  const addToSubgraph = useGraphStore((s) => s.addToSubgraph)
  const setSpotlightVisible = useGraphStore((s) => s.setSpotlightVisible)
  const spotlightActive = spotlightVisible && subgraphNodeKeys.size > 0

  const workspaceGraphSource = (location.state as { workspaceGraphSource?: {
    sourceType: string
    sourceId: string
    sourceLabel: string
    entityKeys: string[]
  } } | null)?.workspaceGraphSource

  /* ---- Dialog states ---- */
  const [addNodeOpen, setAddNodeOpen] = useState(false)
  const [editNodeKey, setEditNodeKey] = useState<string | null>(null)
  const [createRelOpen, setCreateRelOpen] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [expandOpen, setExpandOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)

  /* ---- Side panel (store-driven) ---- */
  const graphPanelCollapsed = useUIStore((s) => s.graphPanelCollapsed)
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)
  const setGraphPanelToolOverlay = useUIStore((s) => s.setGraphPanelToolOverlay)
  const graphPanelToolOverlay = useUIStore((s) => s.graphPanelToolOverlay)

  useEffect(() => {
    if (
      caseLayer === "significant" &&
      graphPanelToolOverlay &&
      ["similar", "cypher", "recycle"].includes(graphPanelToolOverlay)
    ) {
      setGraphPanelToolOverlay(null)
    }
  }, [caseLayer, graphPanelToolOverlay, setGraphPanelToolOverlay])

  // Auto-expand to detail tab when selection changes
  const prevKeysRef = useRef(selectedNodeKeys)
  useEffect(() => {
    const prevKeys = prevKeysRef.current
    prevKeysRef.current = selectedNodeKeys
    const gained = selectedNodeKeys.size > 0 && selectedNodeKeys !== prevKeys
    if (gained) {
      expandGraphPanelTo("detail")
    }
  }, [selectedNodeKeys, expandGraphPanelTo])

  useEffect(() => {
    if (!workspaceGraphSource?.entityKeys?.length) return
    clearSubgraph()
    addToSubgraph(workspaceGraphSource.entityKeys)
    setSpotlightVisible(true)
    selectNodes(workspaceGraphSource.entityKeys)
  }, [
    addToSubgraph,
    clearSubgraph,
    selectNodes,
    setSpotlightVisible,
    workspaceGraphSource,
  ])

  /* ---- Comparison entity details ---- */
  const [compareEntity1, setCompareEntity1] = useState<NodeDetail | null>(null)
  const [compareEntity2, setCompareEntity2] = useState<NodeDetail | null>(null)

  /* ---- Helpers ---- */
  const refreshGraph = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["graph", caseId] })
    queryClient.invalidateQueries({ queryKey: ["graph", "summary", caseId] })
    queryClient.invalidateQueries({ queryKey: ["graph", "entity-types", caseId] })
    queryClient.invalidateQueries({ queryKey: ["graph", "recycle-bin", caseId] })
  }, [queryClient, caseId])

  const mergeTracker = useMergeTracker({ onCompleted: refreshGraph, onPartial: refreshGraph })

  const handleNodeCreated = useCallback(() => refreshGraph(), [refreshGraph])

  const handleExpandNode = useCallback(
    async (key: string) => {
      selectNodes([key])
      setExpandOpen(true)
    },
    [selectNodes]
  )

  const handleDoExpand = useCallback(
    async (depth: number) => {
      if (!caseId) return
      const keys = Array.from(selectedNodeKeys)
      await graphAPI.expandNodes(caseId, keys, depth)
      refreshGraph()
    },
    [caseId, selectedNodeKeys, refreshGraph]
  )

  const handleDeleteNode = useCallback(
    async (key: string) => {
      if (!caseId) return
      await graphAPI.deleteNode(key, caseId, false)
      refreshGraph()
    },
    [caseId, refreshGraph]
  )

  const handleCompareSelected = useCallback(async () => {
    if (!caseId || selectedNodeKeys.size !== 2) return
    const [k1, k2] = Array.from(selectedNodeKeys)
    const [d1, d2] = await Promise.all([
      graphAPI.getNodeDetails(k1, caseId),
      graphAPI.getNodeDetails(k2, caseId),
    ])
    setCompareEntity1(d1)
    setCompareEntity2(d2)
    setCompareOpen(true)
  }, [caseId, selectedNodeKeys])

  const handleCreateSubgraph = useCallback(() => {
    const keys = Array.from(selectedNodeKeys)
    useGraphStore.getState().addToSubgraph(keys)
  }, [selectedNodeKeys])

  /* ---- Merge setup ---- */
  const mergeEntities = useMemo(() => {
    if (selectedNodeKeys.size < 2 || !graphData) return []
    return graphData.nodes.filter((n) => selectedNodeKeys.has(n.key))
  }, [selectedNodeKeys, graphData])

  /* ---- Selected nodes for relationship creation ---- */
  const selectedNodes = useMemo(
    () => graphData?.nodes.filter((n) => selectedNodeKeys.has(n.key)) ?? [],
    [graphData, selectedNodeKeys]
  )

  /* ---- Keyboard shortcuts ---- */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return

      if (e.key === "Escape") {
        selectNodes([])
      }
      if ((e.key === "Delete" || e.key === "Backspace") && hasSelection) {
        // Don't auto-delete — require confirmation via context menu
      }
      if (e.key === "a" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        if (filteredData) selectNodes(filteredData.nodes.map((n) => n.key))
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [selectNodes, hasSelection, filteredData])

  /* ---- Render ---- */
  if (isLoading) {
    return (
      <div className="flex h-full items-start justify-center pt-6">
        <div className="w-full max-w-2xl">
          <LoadProgress caseId={caseId} page="case/graph" since={openedAt} />
        </div>
      </div>
    )
  }

  if (!graphData?.nodes.length) {
    if (caseId && caseLayer === "significant") {
      return (
        <SignificantEmptyState
          caseId={caseId}
          icon={Network}
          eligibleTitle="No available significant entities"
          eligibleDescription="The Significant manifest contains references, but none are currently available in the case graph."
        />
      )
    }
    return (
      <EmptyState
        icon={Network}
        title="No graph data"
        description="Upload and process evidence to populate the knowledge graph"
      />
    )
  }

  const displayData = filteredData ?? graphData

  const graphTypeCounts = new Map<string, number>()
  for (const node of graphData.nodes) {
    graphTypeCounts.set(node.type, (graphTypeCounts.get(node.type) ?? 0) + 1)
  }

  /* Toggle helper for toolbar tool buttons */
  const toggleToolOverlay = (name: typeof graphPanelToolOverlay) =>
    setGraphPanelToolOverlay(graphPanelToolOverlay === name ? null : name)

  return (
    <div className="flex h-full flex-col bg-canvas">
      {workspaceGraphSource?.sourceLabel && (
        <div className="border-b border-border bg-card/95 px-4 py-2 backdrop-blur-sm">
          <div className="flex items-center gap-2 text-xs">
            <Badge variant="outline" className="uppercase">
              {workspaceGraphSource.sourceType}
            </Badge>
            <span className="text-muted-foreground">Spotlight source</span>
            <span className="font-medium">{workspaceGraphSource.sourceLabel}</span>
          </div>
        </div>
      )}
      {graphData?.total_node_count != null && graphData.total_node_count > graphData.nodes.length && (
        <p role="status" className="border-b border-border bg-status-review-soft px-4 py-1.5 text-xs">
          Showing the {graphData.nodes.length.toLocaleString("en-US")} most connected of {graphData.total_node_count.toLocaleString("en-US")} items in this case.
          Search or open a node's neighbours to reach the rest; the Table lists every item.
        </p>
      )}
      <GraphToolbar
        caseId={caseId!}
        graphRef={graphRef}
        graph3dRef={graph3dRef}
        onOpenAddNode={() => setAddNodeOpen(true)}
        onOpenCreateRelationship={() => setCreateRelOpen(true)}
        onOpenForceControls={() => toggleToolOverlay("force-controls")}
        onOpenAnalysis={() => toggleToolOverlay("analysis")}
        onOpenSimilarEntities={() => toggleToolOverlay("similar")}
        onOpenRecycleBin={() => toggleToolOverlay("recycle")}
        onOpenCypher={() => toggleToolOverlay("cypher")}
        scope={caseLayer}
        filteredNodes={filteredNodes}
        totalNodes={totalNodes}
        typeCounts={graphTypeCounts}
      />

      <div className="flex flex-1 overflow-hidden">
        <ResizablePanelGroup orientation="horizontal" className="flex-1">
          {/* Panel 1: Main Graph — always present */}
          <ResizablePanel
            id="graph-canvas"
            order={1}
            defaultSize={graphPanelCollapsed && !spotlightActive ? "100" : "70"}
            minSize="25"
          >
            <div className="relative h-full">
              {graphDimension === "3d" ? (
                <Suspense
                  fallback={
                    <div className="flex h-full items-start justify-center bg-canvas pt-6">
                      <div className="w-full max-w-2xl">
                        <LoadProgress
                          caseId={caseId}
                          page="case/graph"
                          since={openedAt}
                          work={{ step: "Loading the 3D view", done: 0, total: 1 }}
                        />
                      </div>
                    </div>
                  }
                >
                  <GraphCanvas3D data={displayData} graphRef={graph3dRef} />
                </Suspense>
              ) : (
                <GraphCanvas
                  data={displayData}
                  caseId={caseId!}
                  graphRef={graphRef}
                  onLayoutProgress={setLayoutWork}
                />
              )}
              {graphDimension !== "3d" && (
                <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center">
                  <div className="pointer-events-auto w-full max-w-2xl bg-background/90">
                    <LoadProgress caseId={caseId} page="case/graph" since={openedAt} work={layoutWork} />
                  </div>
                </div>
              )}
              <GraphLegend nodes={displayData.nodes} />
            </div>
          </ResizablePanel>

          {/* Panel 2: Spotlight — conditional */}
          {spotlightActive && (
            <>
              <ResizableHandle withHandle />
              <ResizablePanel id="spotlight-column" order={2} defaultSize="30" minSize="15" maxSize="45">
                <SubgraphView caseId={caseId!} graphData={graphData} />
              </ResizablePanel>
            </>
          )}

          {/* Panel 3: Expanded side panel — resizable */}
          {!graphPanelCollapsed && (
            <>
              <ResizableHandle withHandle />
              <ResizablePanel id="graph-side-panel" order={3} defaultSize="30" minSize="15" maxSize="45">
                <GraphSidePanelContent
                  caseId={caseId!}
                  graphData={graphData}
                  onEditNode={(nodeKey) => setEditNodeKey(nodeKey)}
                  onExpandNode={handleExpandNode}
                  onMergeSelected={() => setMergeOpen(true)}
                  onCompareSelected={handleCompareSelected}
                  onCreateSubgraph={handleCreateSubgraph}
                  onRefreshGraph={refreshGraph}
                />
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>

        {/* Collapsed rail — always rendered when collapsed */}
        {graphPanelCollapsed && <GraphSidePanelRail />}
      </div>

      {/* Context menu (floating, positioned by canvas right-click) */}
      <GraphContextMenu
        caseId={caseId!}
        onShowDetail={(key) => {
          selectNodes([key])
          expandGraphPanelTo("detail")
        }}
        onExpand={handleExpandNode}
        onEdit={(key) => {
          setEditNodeKey(key)
        }}
        onDelete={handleDeleteNode}
        onAnalyzeRelationships={(key) => {
          selectNodes([key])
        }}
        onMergeSelected={() => setMergeOpen(true)}
      />

      {/* Dialogs */}
      <AddNodeDialog
        open={addNodeOpen}
        onOpenChange={setAddNodeOpen}
        caseId={caseId!}
        onCreated={handleNodeCreated}
      />
      <EditNodeDialog
        open={!!editNodeKey}
        onOpenChange={(open) => !open && setEditNodeKey(null)}
        nodeKey={editNodeKey}
        caseId={caseId!}
        onSaved={refreshGraph}
      />
      <CreateRelationshipDialog
        open={createRelOpen}
        onOpenChange={setCreateRelOpen}
        sourceNodes={selectedNodes.slice(0, Math.ceil(selectedNodes.length / 2))}
        targetNodes={
          selectedNodes.length >= 2
            ? selectedNodes.slice(Math.ceil(selectedNodes.length / 2))
            : selectedNodes
        }
        caseId={caseId!}
        onCreated={refreshGraph}
      />
      <MergeEntitiesDialog
        open={mergeOpen}
        onOpenChange={(open) => {
          setMergeOpen(open)
          mergeTracker.setDialogOpen(open)
        }}
        entities={mergeEntities}
        caseId={caseId!}
        activeJob={mergeTracker.activeJob}
        onStartTracking={mergeTracker.startTracking}
        onClearJob={mergeTracker.clearJob}
      />
      <ExpandGraphDialog
        open={expandOpen}
        onOpenChange={setExpandOpen}
        nodeCount={selectedNodeKeys.size}
        onExpand={handleDoExpand}
      />
      <EntityComparisonDialog
        open={compareOpen}
        onOpenChange={setCompareOpen}
        entity1={compareEntity1}
        entity2={compareEntity2}
        caseId={caseId!}
      />
    </div>
  )
}
