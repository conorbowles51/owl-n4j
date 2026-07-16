import { useRef, useMemo, useState, useEffect, useCallback } from "react"
import ForceGraph2D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-2d"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Trash2, ChevronDown, ChevronRight } from "lucide-react"
import { useGraphStore } from "@/stores/graph.store"
import { getCanvasColors, getNodeColor } from "@/lib/theme"
import { SubgraphAnalysisPanel } from "./SubgraphAnalysisPanel"
import { useTheme } from "@/lib/use-theme"
import type { GraphData } from "@/types/graph.types"

interface SubgraphViewProps {
  caseId: string
  graphData: GraphData
}

interface SpotlightNode {
  id: string
  key: string
  label: string
  type: string
}

interface SpotlightLink {
  source: string
  target: string
  type: string
}

type ForceNode = NodeObject<SpotlightNode>
type ForceLink = LinkObject<SpotlightNode, SpotlightLink>

export function SubgraphView({ graphData }: SubgraphViewProps) {
  const sgRef = useRef<ForceGraphMethods<SpotlightNode, SpotlightLink> | undefined>(undefined)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 300, height: 300 })
  const [analysisCollapsed, setAnalysisCollapsed] = useState(true)
  const { theme } = useTheme()

  const { subgraphNodeKeys, clearSubgraph, selectNodes, showRelationshipLabels } =
    useGraphStore()

  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)

  const canvasColors = getCanvasColors(isDark)

  /* ---- Resize observer for dynamic sizing ---- */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setDimensions({ width, height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const subgraphData: GraphData = useMemo(() => {
    const nodeSet = subgraphNodeKeys
    const nodes = graphData.nodes.filter((n) => nodeSet.has(n.key))
    const edges = graphData.edges.filter(
      (e) => nodeSet.has(e.source) && nodeSet.has(e.target)
    )
    return { nodes, edges }
  }, [graphData, subgraphNodeKeys])

  const fgData = useMemo(
    () => {
      const nodes: ForceNode[] = subgraphData.nodes.map((n) => ({
        id: n.key,
        key: n.key,
        label: n.label,
        type: n.type,
      }))
      const links: ForceLink[] = subgraphData.edges.map((e) => ({
        source: e.source,
        target: e.target,
        type: e.type,
      }))
      return { nodes, links }
    },
    [subgraphData]
  )

  const handleNodeClick = useCallback(
    (node: ForceNode) => {
      if (node?.key) {
        selectNodes([String(node.key)])
      }
    },
    [selectNodes]
  )

  if (subgraphNodeKeys.size === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-4 text-center">
        <p className="text-sm text-muted-foreground">
          No nodes in Spotlight. Right-click or select nodes and add them to
          the spotlight graph.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-2 shrink-0">
        <h3 className="text-sm font-semibold">
          Spotlight ({subgraphNodeKeys.size})
        </h3>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-red-600 dark:text-red-400"
          onClick={clearSubgraph}
        >
          <Trash2 className="size-3.5" />
          Clear
        </Button>
      </div>

      {/* Force graph — fills available space */}
      <div ref={containerRef} className="flex-1 min-h-0">
        <ForceGraph2D
          ref={sgRef as React.RefObject<ForceGraphMethods<SpotlightNode, SpotlightLink>>}
          graphData={fgData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor={isDark ? "#071820" : "#F4F7F8"}
          nodeCanvasObject={(node: ForceNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const x = node.x ?? 0
            const y = node.y ?? 0
            const sz = 5
            ctx.beginPath()
            ctx.arc(x, y, sz, 0, 2 * Math.PI)
            ctx.fillStyle = getNodeColor(node.type)
            ctx.fill()
            const fontSize = Math.max(9 / globalScale, 2)
            ctx.font = `${fontSize}px "Source Sans 3", system-ui, sans-serif`
            ctx.textAlign = "center"
            ctx.textBaseline = "top"
            ctx.fillStyle = isDark ? "#B6C2C6" : "#46656F"
            const label = (node.label || "").length > 15
              ? (node.label || "").slice(0, 13) + "..."
              : node.label || ""
            ctx.fillText(label, x, y + sz + 2)
          }}
          onNodeClick={handleNodeClick}
          linkColor={() => isDark ? "#294D59" : "#D3DCDF"}
          linkDirectionalArrowLength={3}
          linkCanvasObjectMode={() => (showRelationshipLabels ? "after" : undefined)}
          linkCanvasObject={(link: ForceLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
            if (!showRelationshipLabels || !link.type) return
            const src = link.source as unknown as ForceNode
            const tgt = link.target as unknown as ForceNode
            if (src.x == null || src.y == null || tgt.x == null || tgt.y == null) return
            const midX = (src.x + tgt.x) / 2
            const midY = (src.y + tgt.y) / 2
            const fontSize = Math.max(8 / globalScale, 1.5)
            ctx.font = `${fontSize}px "Source Sans 3", system-ui, sans-serif`
            ctx.textAlign = "center"
            ctx.textBaseline = "middle"

            const text = link.type
            const metrics = ctx.measureText(text)
            const pad = 2 / globalScale
            ctx.fillStyle = canvasColors.labelBg
            ctx.fillRect(
              midX - metrics.width / 2 - pad,
              midY - fontSize / 2 - pad,
              metrics.width + pad * 2,
              fontSize + pad * 2
            )
            ctx.fillStyle = canvasColors.labelText
            ctx.globalAlpha = 0.8
            ctx.fillText(text, midX, midY)
            ctx.globalAlpha = 1.0
          }}
          cooldownTime={2000}
          d3AlphaDecay={0.03}
        />
      </div>

      {/* Collapsible analysis section */}
      <div className="shrink-0 border-t border-border">
        <button
          className="flex w-full items-center gap-1.5 px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
          onClick={() => setAnalysisCollapsed(!analysisCollapsed)}
        >
          {analysisCollapsed ? (
            <ChevronRight className="size-3" />
          ) : (
            <ChevronDown className="size-3" />
          )}
          Analysis
        </button>
        {!analysisCollapsed && (
          <ScrollArea className="max-h-[200px]">
            <SubgraphAnalysisPanel data={subgraphData} className="p-4 pt-0" />
          </ScrollArea>
        )}
      </div>
    </div>
  )
}
