import { getNodeColor } from "@/lib/theme"
import type { GraphData, GraphNode } from "@/types/graph.types"

/** What the 2D canvas has on screen: each node with the position the layout gave it, and the links between them. */
export interface CanvasGraphState {
  nodes: { key: string; x?: number; y?: number }[]
  links: { source: string; target: string; type: string }[]
}

type CanvasSource = () => CanvasGraphState

let source: CanvasSource | null = null

/** The 2D canvas registers itself while mounted so a snapshot can keep where each node sat. */
export function registerCanvasGraphSource(fn: CanvasSource): () => void {
  source = fn
  return () => {
    if (source === fn) source = null
  }
}

export function readCanvasGraph(): CanvasGraphState | null {
  return source ? source() : null
}

function linkEnd(value: unknown): string {
  if (value && typeof value === "object") return String((value as { key?: unknown; id?: unknown }).key ?? (value as { id?: unknown }).id ?? "")
  return String(value ?? "")
}

export function normaliseLinks(links: { source: unknown; target: unknown; type?: unknown }[]) {
  return links.map((l) => ({ source: linkEnd(l.source), target: linkEnd(l.target), type: String(l.type ?? "") }))
}

const SOURCE_KEYS = ["source_files", "source_references", "source_documents"] as const

function sourceRefs(node: GraphNode): string[] {
  const out: string[] = []
  for (const key of SOURCE_KEYS) {
    const value = node.properties?.[key]
    const items = Array.isArray(value) ? value : value ? [value] : []
    for (const item of items) {
      const text = String(item ?? "").trim()
      if (text && !out.includes(text)) out.push(text)
    }
  }
  return out
}

export interface SnapshotSubgraph {
  nodes: {
    key: string
    label: string
    type: string
    color: string
    x?: number
    y?: number
    properties: { source_files?: string[] }
  }[]
  links: { source: string; target: string; type: string }[]
  positions: "canvas" | "none"
}

/**
 * The snapshot of what the investigator sees: the nodes and links on the canvas (hidden nodes are not on it), with
 * their positions, colours and the source files each entity records. Without a 2D canvas (3D view) it falls back
 * to the shown graph without positions, and says so.
 */
export function buildSnapshotSubgraph(shown: GraphData, canvas: CanvasGraphState | null): SnapshotSubgraph {
  const byKey = new Map(shown.nodes.map((n) => [n.key, n]))
  const keys = canvas ? canvas.nodes.map((n) => n.key).filter((k) => byKey.has(k)) : shown.nodes.map((n) => n.key)
  const positions = new Map((canvas?.nodes ?? []).map((n) => [n.key, n]))
  const nodes = keys.map((key) => {
    const node = byKey.get(key)!
    const at = positions.get(key)
    const refs = sourceRefs(node)
    return {
      key,
      label: node.label,
      type: node.type,
      color: getNodeColor(node.type),
      ...(at && Number.isFinite(at.x) && Number.isFinite(at.y) ? { x: at.x, y: at.y } : {}),
      properties: refs.length ? { source_files: refs } : {},
    }
  })
  const inSnapshot = new Set(keys)
  const links = (canvas ? canvas.links : normaliseLinks(shown.edges)).filter(
    (l) => inSnapshot.has(l.source) && inSnapshot.has(l.target),
  )
  return { nodes, links, positions: canvas ? "canvas" : "none" }
}
