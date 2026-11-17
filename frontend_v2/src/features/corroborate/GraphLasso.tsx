import { useRef, useState } from "react"
import type { ForceGraphMethods } from "react-force-graph-2d"
import { Button } from "@/components/ui/button"
import { useSwitch } from "@/lib/ui-switches"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphData } from "@/types/graph.types"
import { hitTest, linksBetween, type Pt } from "./lasso"
import { QuestionMenu } from "./QuestionMenu"
import { addPart } from "./selection-store"

/**
 * Lasso on the Graph (lx-corroselect C): draw round the people, phones, accounts and businesses to corroborate. Each
 * node is tested on its own screen position; the links between the chosen nodes are counted and named. The chosen
 * nodes also become the graph's own selection, so the two agree. A graph that shows only part of the case says so.
 */
export function GraphLasso({ caseId, data, graphRef }: { caseId: string; data: GraphData; graphRef: React.MutableRefObject<ForceGraphMethods | undefined> }) {
  const on = useSwitch("corroborate-v2")
  const [active, setActive] = useState(false)
  const [poly, setPoly] = useState<Pt[]>([])
  const [note, setNote] = useState<string | null>(null)
  const [menu, setMenu] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  if (!on) return null

  const local = (e: React.PointerEvent): Pt => {
    const r = box.current?.getBoundingClientRect()
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }
  }
  const finish = (shape: Pt[]) => {
    setPoly([])
    setActive(false)
    const fg = graphRef.current
    if (!fg || shape.length < 3) return setNote("Draw a closed shape round the items to corroborate.")
    const { hits, unplaced } = hitTest(data.nodes, (n) => (n.x == null || n.y == null ? null : fg.graph2ScreenCoords(n.x, n.y)), shape)
    if (!hits.length) return setNote(`Nothing is inside the shape${unplaced.length ? `; ${unplaced.length} items have no position yet` : ""}.`)
    const inside = new Set(hits.map((n) => n.key))
    const links = linksBetween(data.edges, (e) => [String(typeof e.source === "object" ? (e.source as { key: string }).key : e.source), String(typeof e.target === "object" ? (e.target as { key: string }).key : e.target)], inside)
    selectNodes(hits.map((n) => n.key))
    const capped = data.total_node_count != null && data.total_node_count > data.nodes.length
    addPart(caseId, {
      screen: "the graph",
      label: `Lasso: ${hits.length.toLocaleString("en-US")} items, ${links.length.toLocaleString("en-US")} links between them`,
      members: hits.map((n) => ({ type: "graph_entity", id: n.key, label: n.label })),
      skipped: [],
    })
    setNote(capped ? `The graph shows ${data.nodes.length.toLocaleString("en-US")} of ${data.total_node_count?.toLocaleString("en-US")} items; the lasso covers the items shown.` : null)
    setMenu(true)
  }
  return (
    <>
      <div className="absolute left-2 top-2 z-20 flex flex-col gap-1">
        <Button size="sm" variant={active ? "primary" : "outline"} onClick={() => { setActive(!active); setNote(null) }} aria-pressed={active}>
          {active ? "Draw round items…" : "Lasso to corroborate"}
        </Button>
        {note && <p role="status" className="max-w-56 rounded bg-background/90 px-2 py-1 text-xs">{note}</p>}
      </div>
      {active && (
        <div ref={box} data-testid="graph-lasso" className="absolute inset-0 z-20 cursor-crosshair touch-none"
          onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); setPoly([local(e)]) }}
          onPointerMove={(e) => poly.length && setPoly((p) => [...p, local(e)])}
          onPointerUp={() => finish(poly)}>
          <svg className="pointer-events-none h-full w-full">
            {poly.length > 1 && <polygon points={poly.map((p) => `${p.x},${p.y}`).join(" ")} fill="rgba(59,130,246,0.15)" stroke="rgb(59,130,246)" strokeWidth={2} />}
          </svg>
        </div>
      )}
      {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
    </>
  )
}
