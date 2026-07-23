import { lazy, Suspense, useRef, useMemo, useState, useEffect, useCallback } from "react"
import ForceGraph2D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-2d"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Trash2, ChevronDown, ChevronRight, Star } from "lucide-react"
import { toast } from "sonner"
import { useGraphStore } from "@/stores/graph.store"
import { getCanvasColors, getNodeColor } from "@/lib/theme"
import { SubgraphAnalysisPanel } from "./SubgraphAnalysisPanel"
import { useTheme } from "@/lib/theme-context"
import type { GraphData } from "@/types/graph.types"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  useAddSignificantEntities,
  useSignificantManifest,
} from "@/features/significant/hooks/use-significant"
import { useCaseLayerStore } from "@/features/significant/stores/case-layer.store"
import { LoadingSpinner } from "@/components/ui/loading-spinner"

const GraphCanvas3D = lazy(() =>
  import("./GraphCanvas3D").then((module) => ({ default: module.GraphCanvas3D }))
)

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

export function SubgraphView({ caseId, graphData }: SubgraphViewProps) {
  const sgRef = useRef<ForceGraphMethods<SpotlightNode, SpotlightLink> | undefined>(undefined)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 300, height: 300 })
  const [analysisCollapsed, setAnalysisCollapsed] = useState(true)
  const [confirmSignificantOpen, setConfirmSignificantOpen] = useState(false)
  const { theme } = useTheme()

  const { subgraphNodeKeys, clearSubgraph, selectNodes, showRelationshipLabels, graphDimension } =
    useGraphStore()
  const { entityKeySet: significantEntityKeys } = useSignificantManifest(caseId)
  const addSignificant = useAddSignificantEntities(caseId)
  const setLayer = useCaseLayerStore((state) => state.setLayer)

  const spotlightKeys = useMemo(
    () => Array.from(subgraphNodeKeys),
    [subgraphNodeKeys]
  )
  const newSignificantCount = useMemo(
    () => spotlightKeys.filter((key) => !significantEntityKeys.has(key)).length,
    [significantEntityKeys, spotlightKeys]
  )

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

  const addSpotlightToSignificant = useCallback(async () => {
    try {
      const result = await addSignificant.mutateAsync({
        entityKeys: spotlightKeys,
        source: "spotlight",
        context: { surface: "spotlight", spotlight_size: spotlightKeys.length },
      })
      setConfirmSignificantOpen(false)
      const added = result.added_count ?? 0
      toast.success(
        added === 1
          ? "1 entity added to Significant"
          : `${added.toLocaleString()} entities added to Significant`,
        {
          action: {
            label: "View Significant",
            onClick: () => setLayer(caseId, "significant"),
          },
        }
      )
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not add Spotlight to Significant"
      )
    }
  }, [addSignificant, caseId, setLayer, spotlightKeys])

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
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-7 border-amber-500/30 bg-amber-500/10 text-xs text-amber-700 hover:bg-amber-500/15 dark:text-amber-300"
            disabled={newSignificantCount === 0 || addSignificant.isPending}
            onClick={() => setConfirmSignificantOpen(true)}
          >
            <Star className="size-3.5" />
            {newSignificantCount === 0
              ? "All significant"
              : `Add ${newSignificantCount.toLocaleString()} to Significant`}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-red-600 dark:text-red-400"
            onClick={clearSubgraph}
          >
            <Trash2 className="size-3.5" />
            Clear
          </Button>
        </div>
      </div>

      {/* Force graph — fills available space */}
      <div ref={containerRef} className="flex-1 min-h-0">
        {graphDimension === "3d" ? (
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center bg-canvas">
                <LoadingSpinner size="sm" />
              </div>
            }
          >
            <GraphCanvas3D data={subgraphData} variant="spotlight" />
          </Suspense>
        ) : (
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
        )}
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

      <Dialog open={confirmSignificantOpen} onOpenChange={setConfirmSignificantOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Spotlight to Significant?</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>
              This will add {newSignificantCount.toLocaleString()} new
              {newSignificantCount === 1 ? " entity" : " entities"} to the shared
              Significant layer. {spotlightKeys.length - newSignificantCount > 0
                ? `${(spotlightKeys.length - newSignificantCount).toLocaleString()} are already included.`
                : null}
            </p>
            <p className="rounded-md border border-amber-500/20 bg-amber-500/[0.07] px-3 py-2 text-xs text-foreground/80">
              Relationships will appear automatically wherever both connected
              entities are significant. Your Spotlight will remain unchanged.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmSignificantOpen(false)}
              disabled={addSignificant.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => void addSpotlightToSignificant()}
              disabled={addSignificant.isPending || newSignificantCount === 0}
            >
              <Star className="size-3.5" />
              {addSignificant.isPending
                ? "Adding…"
                : `Add ${newSignificantCount.toLocaleString()}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
