import { useMemo } from "react"
import type { GraphData, GraphNode } from "@/types/graph.types"
import { useGraphStore } from "@/stores/graph.store"

interface LayoutNode extends GraphNode {
  x: number
  y: number
}

interface LayoutResult {
  nodes: LayoutNode[]
}

function forceLayout(data: GraphData, width: number, height: number): LayoutResult {
  // Simple force-directed placement using existing positions or circular fallback
  const nodes = data.nodes.map((node, i) => ({
    ...node,
    x: node.x ?? width / 2 + Math.cos((2 * Math.PI * i) / data.nodes.length) * Math.min(width, height) * 0.35,
    y: node.y ?? height / 2 + Math.sin((2 * Math.PI * i) / data.nodes.length) * Math.min(width, height) * 0.35,
  }))
  return { nodes }
}

function hierarchicalLayout(data: GraphData, width: number, height: number): LayoutResult {
  // Top-down hierarchical: group by connection count (more connections = higher)
  const connectionCount = new Map<string, number>()
  data.nodes.forEach((n) => connectionCount.set(n.key, 0))
  data.edges.forEach((e) => {
    connectionCount.set(e.source, (connectionCount.get(e.source) ?? 0) + 1)
    connectionCount.set(e.target, (connectionCount.get(e.target) ?? 0) + 1)
  })

  const sorted = [...data.nodes].sort(
    (a, b) => (connectionCount.get(b.key) ?? 0) - (connectionCount.get(a.key) ?? 0)
  )
  const levels = 5
  const perLevel = Math.ceil(sorted.length / levels)

  const nodes = sorted.map((node, i) => {
    const level = Math.floor(i / perLevel)
    const indexInLevel = i % perLevel
    const nodesInLevel = Math.min(perLevel, sorted.length - level * perLevel)
    return {
      ...node,
      x: ((indexInLevel + 1) / (nodesInLevel + 1)) * width,
      y: ((level + 1) / (levels + 1)) * height,
    }
  })
  return { nodes }
}

function radialLayout(data: GraphData, width: number, height: number): LayoutResult {
  const cx = width / 2
  const cy = height / 2
  const maxRadius = Math.min(width, height) * 0.4
  const nodes = data.nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / data.nodes.length
    const radius = maxRadius * (0.5 + 0.5 * (i % 3) / 2)
    return {
      ...node,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    }
  })
  return { nodes }
}

function circularLayout(data: GraphData, width: number, height: number): LayoutResult {
  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) * 0.38
  const nodes = data.nodes.map((node, i) => ({
    ...node,
    x: cx + Math.cos((2 * Math.PI * i) / data.nodes.length) * radius,
    y: cy + Math.sin((2 * Math.PI * i) / data.nodes.length) * radius,
  }))
  return { nodes }
}

const layoutFns = {
  force: forceLayout,
  hierarchical: hierarchicalLayout,
  radial: radialLayout,
  circular: circularLayout,
}

export function useGraphLayout(
  data: GraphData | undefined,
  width = 800,
  height = 600
): LayoutResult | undefined {
  const { viewSettings } = useGraphStore()

  return useMemo(() => {
    if (!data || data.nodes.length === 0) return undefined
    const fn = layoutFns[viewSettings.layout]
    return fn(data, width, height)
  }, [data, viewSettings.layout, width, height])
}
