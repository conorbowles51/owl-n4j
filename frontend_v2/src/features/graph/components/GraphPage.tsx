import { useRef, useState, useCallback, useEffect, useMemo } from "react"
import { useParams } from "react-router-dom"
import type { ForceGraphMethods } from "react-force-graph-2d"
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
import { NodeDetailSheet } from "./NodeDetailSheet"
import { AddNodeDialog } from "./AddNodeDialog"
import { EditNodeDialog } from "./EditNodeDialog"
import { CreateRelationshipDialog } from "./CreateRelationshipDialog"
import { MergeEntitiesDialog } from "./MergeEntitiesDialog"
import { ExpandGraphDialog } from "./ExpandGraphDialog"
import { EntityComparisonSheet } from "./EntityComparisonSheet"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { Network } from "lucide-react"
import { graphAPI } from "../api"
import type { GraphNode, NodeDetail } from "@/types/graph.types"

/* ------------------------------------------------------------------ */
/*  Side panel modes                                                    */
/* ------------------------------------------------------------------ */

type SidePanelMode =
  | "detail"
  | "force-controls"
  | "analysis"
  | "similar"
  | "cypher"
  | "recycle"
  | null

/* ------------------------------------------------------------------ */
/*  Lazy-loaded panels (to avoid loading all code upfront)             */
/* ------------------------------------------------------------------ */

import { ForceControlsPanel } from "./ForceControlsPanel"
import { GraphAnalysisPanel } from "./GraphAnalysisPanel"
import { RecycleBinPanel } from "./RecycleBinPanel"
import { CypherPanel } from "./CypherPanel"
import { SubgraphView } from "./SubgraphView"
import { SimilarEntitiesView } from "./SimilarEntitiesView"

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function GraphPage() {
  const { id: caseId } = useParams()
  const queryClient = useQueryClient()
  const { data: graphData, isLoading } = useGraphData(caseId)
  const { filteredData } = useGraphSearch(graphData)
  const graphRef = useRef<ForceGraphMethods>()

  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const hasSelection = selectedNodeKeys.size > 0

  /* ---- Spotlight state ---- */
  const spotlightVisible = useGraphStore((s) => s.spotlightVisible)
  const subgraphNodeKeys = useGraphStore((s) => s.subgraphNodeKeys)
  const spotlightActive = spotlightVisible && subgraphNodeKeys.size > 0

  /* ---- Dialog states ---- */
  const [addNodeOpen, setAddNodeOpen] = useState(false)
  const [editNode, setEditNode] = useState<GraphNode | null>(null)
  const [createRelOpen, setCreateRelOpen] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [expandOpen, setExpandOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)

  /* ---- Side panel ---- */
  const [sidePanel, setSidePanel] = useState<SidePanelMode>(null)

  // Auto-show detail panel on selection
  useEffect(() => {
    if (hasSelection && sidePanel === null) {
      setSidePanel("detail")
    } else if (!hasSelection && sidePanel === "detail") {
      setSidePanel(null)
    }
  }, [hasSelection, sidePanel])

  /* ---- Comparison entity details ---- */
  const [compareEntity1, setCompareEntity1] = useState<NodeDetail | null>(null)
  const [compareEntity2, setCompareEntity2] = useState<NodeDetail | null>(null)

  /* ---- Helpers ---- */
  const refreshGraph = () =>
    queryClient.invalidateQueries({ queryKey: ["graph", caseId] })

  const handleNodeCreated = useCallback(() => refreshGraph(), [])

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
    [caseId, selectedNodeKeys]
  )

  const handleDeleteNode = useCallback(
    async (key: string) => {
      if (!caseId) return
      await graphAPI.deleteNode(key, caseId, false)
      refreshGraph()
    },
    [caseId]
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
    if (selectedNodeKeys.size !== 2 || !graphData) return { e1: null, e2: null }
    const [k1, k2] = Array.from(selectedNodeKeys)
    return {
      e1: graphData.nodes.find((n) => n.key === k1) ?? null,
      e2: graphData.nodes.find((n) => n.key === k2) ?? null,
    }
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
      if (e.key === "f" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        // Focus search handled by toolbar
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [selectNodes, hasSelection, filteredData])

  /* ---- Render ---- */
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!graphData?.nodes.length) {
    return (
      <EmptyState
        icon={Network}
        title="No graph data"
        description="Upload and process evidence to populate the knowledge graph"
      />
    )
  }

  const displayData = filteredData ?? graphData
  const showRightPanel = sidePanel !== null

  /* Compute default sizes based on active columns */
  const mainDefault = spotlightActive && showRightPanel ? "40" : spotlightActive || showRightPanel ? "60" : "100"

  return (
    <div className="flex h-full flex-col">
      <GraphToolbar
        caseId={caseId!}
        graphRef={graphRef as any}
        onOpenAddNode={() => setAddNodeOpen(true)}
        onOpenCreateRelationship={() => setCreateRelOpen(true)}
        onOpenForceControls={() =>
          setSidePanel(sidePanel === "force-controls" ? null : "force-controls")
        }
        onOpenAnalysis={() =>
          setSidePanel(sidePanel === "analysis" ? null : "analysis")
        }
        onOpenSimilarEntities={() =>
          setSidePanel(sidePanel === "similar" ? null : "similar")
        }
        onOpenRecycleBin={() =>
          setSidePanel(sidePanel === "recycle" ? null : "recycle")
        }
        onOpenCypher={() =>
          setSidePanel(sidePanel === "cypher" ? null : "cypher")
        }
      />

      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        {/* Panel 1: Main Graph — always present */}
        <ResizablePanel
          id="graph-canvas"
          order={1}
          defaultSize={mainDefault}
          minSize="25"
        >
          <div className="relative h-full">
            <GraphCanvas
              data={displayData}
              caseId={caseId!}
              graphRef={graphRef as any}
            />
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

        {/* Panel 3: Detail / Tool panels — conditional */}
        {showRightPanel && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel id="graph-side-panel" order={3} defaultSize="30" minSize="15" maxSize="45">
              {sidePanel === "detail" && (
                <NodeDetailSheet
                  caseId={caseId!}
                  graphData={graphData}
                  onEditNode={(node) => setEditNode(node)}
                  onExpandNode={handleExpandNode}
                  onMergeSelected={() => setMergeOpen(true)}
                  onCompareSelected={handleCompareSelected}
                  onCreateSubgraph={handleCreateSubgraph}
                />
              )}
              {sidePanel === "force-controls" && <ForceControlsPanel />}
              {sidePanel === "analysis" && (
                <GraphAnalysisPanel caseId={caseId!} />
              )}
              {sidePanel === "similar" && (
                <SimilarEntitiesView
                  caseId={caseId!}
                  graphData={graphData}
                  onRefresh={refreshGraph}
                />
              )}
              {sidePanel === "cypher" && (
                <CypherPanel caseId={caseId!} className="p-4" />
              )}
              {sidePanel === "recycle" && (
                <RecycleBinPanel caseId={caseId!} />
              )}
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      {/* Context menu (floating, positioned by canvas right-click) */}
      <GraphContextMenu
        onShowDetail={(key) => {
          selectNodes([key])
          setSidePanel("detail")
        }}
        onExpand={handleExpandNode}
        onEdit={(key) => {
          const node = graphData.nodes.find((n) => n.key === key)
          if (node) setEditNode(node)
        }}
        onDelete={handleDeleteNode}
        onAnalyzeRelationships={(key) => {
          selectNodes([key])
          // Could open a relationship analysis modal here
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
        open={!!editNode}
        onOpenChange={(open) => !open && setEditNode(null)}
        node={editNode}
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
        onOpenChange={setMergeOpen}
        entity1={mergeEntities.e1}
        entity2={mergeEntities.e2}
        caseId={caseId!}
        onMerged={refreshGraph}
      />
      <ExpandGraphDialog
        open={expandOpen}
        onOpenChange={setExpandOpen}
        nodeCount={selectedNodeKeys.size}
        onExpand={handleDoExpand}
      />
      <EntityComparisonSheet
        open={compareOpen}
        onOpenChange={setCompareOpen}
        entity1={compareEntity1}
        entity2={compareEntity2}
      />
    </div>
  )
}
