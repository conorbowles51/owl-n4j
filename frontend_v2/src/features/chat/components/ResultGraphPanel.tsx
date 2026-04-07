import { useRef, useCallback, useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import {
  PanelRightClose,
  PanelRightOpen,
  Network,
  Maximize2,
} from "lucide-react"
import ForceGraph2D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-2d"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { cn } from "@/lib/cn"
import { getNodeColor, getCanvasColors } from "@/lib/theme"
import { useTheme } from "@/lib/theme-provider"
import { graphAPI } from "@/features/graph/api"
import { useChatStore } from "../stores/chat.store"
import { useResultGraph } from "../hooks/use-result-graph"
import { ResultNodeDetail } from "./ResultNodeDetail"
import type { ResultGraphNode, ResultGraphLink } from "../types"
import type { GraphEdge, GraphNode } from "@/types/graph.types"

interface FGNode extends ResultGraphNode {
  x?: number
  y?: number
}

interface FGLink {
  source: string | FGNode
  target: string | FGNode
  type: string
  properties?: Record<string, unknown>
}

export function ResultGraphPanel() {
  const { id: caseId } = useParams()
  const graphRef = useRef<
    ForceGraphMethods<NodeObject<FGNode>, LinkObject<FGNode, FGLink>> | undefined
  >(undefined)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    node: FGNode
  } | null>(null)

  const { theme } = useTheme()
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  const canvasColors = getCanvasColors(isDark)

  const isOpen = useChatStore((s) => s.resultGraphPanelOpen)
  const setOpen = useChatStore((s) => s.setResultGraphPanelOpen)
  const appendResultGraph = useChatStore((s) => s.appendResultGraph)

  const {
    mode,
    setMode,
    displayGraph,
    selectedNodeKey,
    setSelectedNodeKey,
    selectedNode,
    isEmpty,
    nodeCount,
  } = useResultGraph()

  // Track container size
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        })
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [isOpen])

  // Zoom to fit when graph data changes
  useEffect(() => {
    if (displayGraph.nodes.length > 0 && graphRef.current) {
      setTimeout(() => graphRef.current?.zoomToFit(400, 40), 300)
    }
  }, [displayGraph])

  const handleNodeClick = useCallback(
    (node: FGNode) => {
      setSelectedNodeKey(node.key === selectedNodeKey ? null : node.key)
      setContextMenu(null)
    },
    [selectedNodeKey, setSelectedNodeKey]
  )

  const handleNodeRightClick = useCallback(
    (node: FGNode, event: MouseEvent) => {
      event.preventDefault()
      setContextMenu({ x: event.clientX, y: event.clientY, node })
    },
    []
  )

  const handleExpandNeighbors = useCallback(
    async (nodeKey: string) => {
      if (!caseId) return
      try {
        const data = await graphAPI.getNodeNeighbours(nodeKey, 1, caseId)
        // Convert graph data to result graph format and merge
        const newNodes = data.nodes.map((node: GraphNode) => ({
          key: node.key,
          name: node.label || node.key,
          type: node.type || "unknown",
          confidence: 0.5,
          mentioned: false,
          relevance_reason: "Expanded from neighbor",
          relevance_source: "graph",
        }))
        const newLinks = data.edges.map((edge: GraphEdge) => ({
          source: edge.source,
          target: edge.target,
          type: edge.type || "RELATED",
        }))
        appendResultGraph({ nodes: newNodes, links: newLinks })
      } catch {
        // Silent fail
      }
      setContextMenu(null)
    },
    [caseId, appendResultGraph]
  )

  const handleBackgroundClick = useCallback(() => {
    setSelectedNodeKey(null)
    setContextMenu(null)
  }, [setSelectedNodeKey])

  const handleZoomToFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 40)
  }, [])

  // Node paint function
  const paintNode = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const size = 4 + Math.min(node.confidence * 8, 8)
      const color = getNodeColor(node.type)
      const isSelected = node.key === selectedNodeKey
      const alpha = node.mentioned ? 1.0 : 0.5

      // Selection ring
      if (isSelected) {
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, size + 2, 0, 2 * Math.PI)
        ctx.strokeStyle = "#f59e0b"
        ctx.lineWidth = 1.5 / globalScale
        ctx.stroke()
      }

      // Node circle
      ctx.beginPath()
      ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.globalAlpha = alpha
      ctx.fill()
      ctx.globalAlpha = 1

      // Label
      const label = node.name.length > 16
        ? node.name.slice(0, 14) + "..."
        : node.name
      const fontSize = Math.max(10 / globalScale, 2)
      ctx.font = `${fontSize}px sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "top"
      ctx.fillStyle = isSelected ? "#f59e0b" : canvasColors.labelText
      ctx.fillText(label, node.x!, node.y! + size + 2)
    },
    [selectedNodeKey, canvasColors]
  )

  // Link paint function
  const paintLink = useCallback(
    (
      link: FGLink,
      ctx: CanvasRenderingContext2D,
      globalScale: number
    ) => {
      const source = link.source as FGNode
      const target = link.target as FGNode
      if (!source.x || !target.x) return

      ctx.beginPath()
      ctx.moveTo(source.x!, source.y!)
      ctx.lineTo(target.x!, target.y!)
      ctx.strokeStyle = canvasColors.linkColor
      ctx.lineWidth = 0.5 / globalScale
      ctx.stroke()

      // Link label at midpoint
      if (globalScale > 1.5) {
        const mx = (source.x! + target.x!) / 2
        const my = (source.y! + target.y!) / 2
        const fontSize = Math.max(8 / globalScale, 1.5)
        ctx.font = `${fontSize}px sans-serif`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillStyle = canvasColors.labelText
        ctx.fillText((link as ResultGraphLink).type, mx, my)
      }
    },
    [canvasColors]
  )

  // Collapsed state — just a rail with toggle button
  if (!isOpen) {
    return (
      <div className="flex flex-col items-center border-l border-border py-2 px-1 gap-2">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setOpen(true)}
          title="Open result graph"
        >
          <PanelRightOpen className="size-4" />
        </Button>
        {nodeCount > 0 && (
          <span className="text-[10px] text-amber-500 font-medium">
            {nodeCount}
          </span>
        )}
      </div>
    )
  }

  // Expanded state — fills parent ResizablePanel
  return (
    <div className="flex h-full flex-col border-l border-border">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-1">
        <div className="flex items-center gap-2">
          <Network className="size-3.5 text-amber-500" />
          <span className="text-xs font-semibold">Result Graph</span>
          {nodeCount > 0 && (
            <span className="text-[10px] text-muted-foreground">
              {nodeCount} entities
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleZoomToFit}
            title="Zoom to fit"
          >
            <Maximize2 className="size-3" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setOpen(false)}
          >
            <PanelRightClose className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Mode toggle */}
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-1.5">
        <div className="flex rounded-md border border-border bg-muted/50 p-0.5">
          <button
            className={cn(
              "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
              mode === "cumulative"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setMode("cumulative")}
          >
            Full Conversation
          </button>
          <button
            className={cn(
              "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
              mode === "last"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setMode("last")}
          >
            Last Response
          </button>
        </div>
      </div>

      {/* Graph area */}
      <div ref={containerRef} className="relative flex-1 overflow-hidden">
        {isEmpty ? (
          <EmptyState
            icon={Network}
            title="No entities yet"
            description="Ask a question to see relevant entities here"
            className="h-full"
          />
        ) : (
          <>
            <ForceGraph2D
              ref={graphRef}
              width={dimensions.width || 320}
              height={dimensions.height || 400}
              graphData={{
                nodes: displayGraph.nodes as FGNode[],
                links: displayGraph.links as unknown as FGLink[],
              }}
              nodeId="key"
              linkSource="source"
              linkTarget="target"
              nodeCanvasObject={paintNode}
              linkCanvasObject={paintLink}
              nodePointerAreaPaint={(node: FGNode, color, ctx) => {
                const size = 4 + Math.min(node.confidence * 8, 8) + 3
                ctx.beginPath()
                ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI)
                ctx.fillStyle = color
                ctx.fill()
              }}
              onNodeClick={handleNodeClick}
              onNodeRightClick={handleNodeRightClick}
              onBackgroundClick={handleBackgroundClick}
              cooldownTime={2000}
              d3AlphaDecay={0.04}
              d3VelocityDecay={0.3}
              enableNodeDrag
              enableZoomInteraction
            />

            {/* Context menu overlay */}
            {contextMenu && (
              <div
                className="fixed z-50 min-w-40 rounded-md border border-border bg-background p-1 shadow-lg"
                style={{ left: contextMenu.x, top: contextMenu.y }}
              >
                <button
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-muted"
                  onClick={() => handleExpandNeighbors(contextMenu.node.key)}
                >
                  <Network className="size-3.5" />
                  Expand Neighbors
                </button>
                <button
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-muted"
                  onClick={() => {
                    window.location.href = `/cases/${caseId}/graph?select=${contextMenu.node.key}`
                    setContextMenu(null)
                  }}
                >
                  <Maximize2 className="size-3.5" />
                  View in Main Graph
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Selected node detail */}
      {selectedNode && (
        <ResultNodeDetail
          node={selectedNode}
          onClose={() => setSelectedNodeKey(null)}
        />
      )}
    </div>
  )
}
