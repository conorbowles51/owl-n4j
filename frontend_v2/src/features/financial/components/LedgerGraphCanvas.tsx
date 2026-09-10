import { useEffect, useMemo, useRef, useState } from "react"
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d"
import { Button } from "@/components/ui/button"
import type { PostingGraph } from "../lib/ledger-graph"
import { correctionMoney } from "../lib/correction-contract"
type Node = PostingGraph["nodes"][number]
type Edge = PostingGraph["edges"][number]
export default function LedgerGraphCanvas({
  data,
  onNode,
  onSource,
}: {
  data: PostingGraph
  onNode: (id: string) => void
  onSource: (id: string) => void
}) {
  const container = useRef<HTMLDivElement>(null),
    graph = useRef<ForceGraphMethods<Node, Edge> | undefined>(undefined)
  const [width, setWidth] = useState(800)
  const fitted = useRef(false)
  const graphData = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ ...e })),
    }),
    [data]
  )
  useEffect(() => {
    const el = container.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      if (entries[0].contentRect.width > 0)
        setWidth(entries[0].contentRect.width)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const tooltip = (text: string) => {
    const el = document.createElement("span")
    el.textContent = text
    return el.innerHTML
  }
  return (
    <div ref={container} className="overflow-hidden rounded border">
      <div className="flex items-center justify-between gap-2 p-2">
        <p>
          Drag to move; scroll to zoom. Select a node to list its postings, or
          an arrow to inspect its source.
        </p>
        <Button
          variant="outline"
          onClick={() => graph.current?.zoomToFit(300, 40)}
        >
          Fit graph
        </Button>
      </div>
      <ForceGraph2D
        ref={graph}
        graphData={graphData}
        width={width}
        height={440}
        backgroundColor="#101318"
        nodeId="id"
        nodeLabel={(n) => tooltip(n.label)}
        linkLabel={(e) =>
          tooltip(
            `${correctionMoney(e.amount_minor, e.currency)} · ${e.ordering_date} · ${e.description ?? "No description"}`
          )
        }
        nodeColor={(n) => (n.kind === "account" ? "#ef5269" : "#7abaf5")}
        nodeVal={(n) => (n.kind === "account" ? 8 : 4)}
        linkColor={() => "#8e9caf"}
        linkDirectionalArrowLength={5}
        linkDirectionalArrowRelPos={0.85}
        linkCurvature={0.12}
        cooldownTicks={100}
        onNodeClick={(n) => onNode(n.id)}
        onLinkClick={(e) => onSource(e.transaction_id)}
        onEngineStop={() => {
          if (!fitted.current) {
            fitted.current = true
            graph.current?.zoomToFit(300, 40)
          }
        }}
        nodeCanvasObjectMode={() => "after"}
        nodeCanvasObject={(node, ctx, scale) => {
          ctx.font = `${11 / scale}px sans-serif`
          ctx.fillStyle = "#e3e9f2"
          ctx.textAlign = "center"
          ctx.textBaseline = "top"
          ctx.fillText(
            node.label.length > 28 ? node.label.slice(0, 27) + "…" : node.label,
            node.x ?? 0,
            (node.y ?? 0) + 7
          )
        }}
      />
    </div>
  )
}
