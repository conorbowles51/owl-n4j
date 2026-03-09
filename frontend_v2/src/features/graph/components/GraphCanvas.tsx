import { useRef, useEffect, useCallback, useMemo, useState } from "react"
import ForceGraph2D, {
  type ForceGraphMethods,
  type NodeObject,
  type LinkObject,
} from "react-force-graph-2d"
import { useGraphStore } from "@/stores/graph.store"
import { getNodeColor, communityColors } from "@/lib/theme"
import type { GraphData, GraphNode, GraphEdge } from "@/types/graph.types"

/* ------------------------------------------------------------------ */
/*  Types for react-force-graph-2d                                     */
/* ------------------------------------------------------------------ */

interface FGNode extends NodeObject {
  id: string
  key: string
  label: string
  type: string
  confidence?: number
  community_id?: number
  mentioned?: boolean
  _degree?: number
}

interface FGLink extends LinkObject {
  type: string
  weight?: number
}

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface GraphCanvasProps {
  data: GraphData
  caseId: string
  graphRef?: React.MutableRefObject<ForceGraphMethods<FGNode, FGLink> | undefined>
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function GraphCanvas({ data, caseId: _caseId, graphRef: externalRef }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const internalRef = useRef<ForceGraphMethods<FGNode, FGLink>>()
  const fgRef = externalRef ?? internalRef
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const hasZoomedToFit = useRef(false)

  const {
    selectedNodeKeys,
    selectNodes,
    addToSelection,
    hiddenNodeKeys,
    pinnedNodeKeys,
    linkDistance,
    chargeStrength,
    centerStrength,
    showRelationshipLabels,
    communityMap,
    highlightedPaths,
    analysisHighlight,
    selectionMode,
    openContextMenu,
  } = useGraphStore()

  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  /* ---- Drag selection state ---- */
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [dragEnd, setDragEnd] = useState<{ x: number; y: number } | null>(null)
  const isDragging = useRef(false)

  /* ---- Resize observer ---- */
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

  /* ---- Build force-graph data with degree calc ---- */
  const fgData = useMemo(() => {
    const visibleNodes = data.nodes.filter((n) => !hiddenNodeKeys.has(n.key))
    const visibleKeys = new Set(visibleNodes.map((n) => n.key))

    const degreeCounts = new Map<string, number>()
    for (const e of data.edges) {
      if (visibleKeys.has(e.source) && visibleKeys.has(e.target)) {
        degreeCounts.set(e.source, (degreeCounts.get(e.source) ?? 0) + 1)
        degreeCounts.set(e.target, (degreeCounts.get(e.target) ?? 0) + 1)
      }
    }

    const nodes: FGNode[] = visibleNodes.map((n) => {
      const isPinned = pinnedNodeKeys.has(n.key)
      return {
        id: n.key,
        key: n.key,
        label: n.label,
        type: n.type,
        confidence: n.confidence,
        community_id: n.community_id,
        mentioned: n.mentioned,
        _degree: degreeCounts.get(n.key) ?? 0,
        ...(isPinned && n.x != null && n.y != null
          ? { fx: n.x, fy: n.y }
          : {}),
      }
    })

    const links: FGLink[] = data.edges
      .filter((e) => visibleKeys.has(e.source) && visibleKeys.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        type: e.type,
        weight: e.weight,
      }))

    return { nodes, links }
  }, [data, hiddenNodeKeys, pinnedNodeKeys])

  /* ---- Apply force parameters ---- */
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force("link")?.distance(linkDistance)
    fg.d3Force("charge")?.strength(chargeStrength)
    fg.d3Force("center")?.strength(centerStrength)
    fg.d3ReheatSimulation()
  }, [linkDistance, chargeStrength, centerStrength, fgRef])

  /* ---- Auto zoom-to-fit on first data load ---- */
  const handleEngineStop = useCallback(() => {
    if (!hasZoomedToFit.current && fgRef.current && fgData.nodes.length > 0) {
      hasZoomedToFit.current = true
      setTimeout(() => fgRef.current?.zoomToFit(400, 50), 100)
    }
  }, [fgRef, fgData.nodes.length])

  /* ---- Node color logic ---- */
  const getColor = useCallback(
    (node: FGNode): string => {
      if (communityMap?.has(node.key)) {
        const cid = communityMap.get(node.key)!
        return communityColors[cid % communityColors.length]
      }
      return getNodeColor(node.type)
    },
    [communityMap]
  )

  /* ---- Custom node renderer ---- */
  const paintNode = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0
      const y = node.y ?? 0
      const isSelected = selectedNodeKeys.has(node.key)
      const isHovered = hoveredNode === node.key
      const isHighlighted = analysisHighlight?.has(node.key) ?? false
      const isOnPath = highlightedPaths?.has(node.key) ?? false

      // Size by degree, scaled by confidence
      const baseSz = 4 + Math.min((node._degree ?? 0) * 0.8, 12)
      const confFactor = node.confidence != null ? 0.7 + node.confidence * 1.3 : 1
      const sz = baseSz * confFactor

      // Opacity based on mentioned flag
      const alpha = node.mentioned === false ? 0.45 : 1.0

      const color = getColor(node)

      ctx.globalAlpha = alpha

      // Glow for highlighted nodes
      if (isHighlighted || isOnPath) {
        ctx.beginPath()
        ctx.arc(x, y, sz + 4, 0, 2 * Math.PI)
        ctx.fillStyle = isOnPath ? "rgba(59,130,246,0.25)" : "rgba(245,158,11,0.25)"
        ctx.fill()
      }

      // Selection ring
      if (isSelected) {
        ctx.beginPath()
        ctx.arc(x, y, sz + 2.5, 0, 2 * Math.PI)
        ctx.strokeStyle = "#3B82F6"
        ctx.lineWidth = 2 / globalScale
        ctx.stroke()
      }

      // Hover ring
      if (isHovered && !isSelected) {
        ctx.beginPath()
        ctx.arc(x, y, sz + 2, 0, 2 * Math.PI)
        ctx.strokeStyle = "#94A3B8"
        ctx.lineWidth = 1.5 / globalScale
        ctx.stroke()
      }

      // Node circle
      ctx.beginPath()
      ctx.arc(x, y, sz, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()

      // Label
      const fontSize = Math.max(10 / globalScale, 2)
      ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "top"
      ctx.fillStyle = "#AAB7C7"
      const label =
        node.label.length > 20
          ? node.label.slice(0, 18) + "..."
          : node.label
      ctx.fillText(label, x, y + sz + 2)

      ctx.globalAlpha = 1.0
    },
    [selectedNodeKeys, hoveredNode, getColor, analysisHighlight, highlightedPaths]
  )

  /* ---- Custom link renderer ---- */
  const paintLink = useCallback(
    (link: FGLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const src = link.source as FGNode
      const tgt = link.target as FGNode
      if (!src?.x || !tgt?.x) return

      const isOnPath =
        highlightedPaths?.has((src as FGNode).key) &&
        highlightedPaths?.has((tgt as FGNode).key)

      const width = Math.max(0.5, (link.weight ?? 1) * 0.8) / Math.sqrt(globalScale)
      ctx.beginPath()
      ctx.moveTo(src.x, src.y!)
      ctx.lineTo(tgt.x, tgt.y!)
      ctx.strokeStyle = isOnPath ? "#3B82F6" : "#2D3A4F"
      ctx.lineWidth = isOnPath ? width * 2 : width
      ctx.globalAlpha = isOnPath ? 0.9 : 0.4
      ctx.stroke()

      // Arrowhead
      const dx = tgt.x - src.x
      const dy = tgt.y! - src.y!
      const len = Math.sqrt(dx * dx + dy * dy)
      if (len < 1) return

      const tgtSz = 4 + Math.min(((tgt as FGNode)._degree ?? 0) * 0.8, 12)
      const arrowLen = 4 / globalScale
      const endX = tgt.x - (dx / len) * (tgtSz + 1)
      const endY = tgt.y! - (dy / len) * (tgtSz + 1)
      const angle = Math.atan2(dy, dx)

      ctx.beginPath()
      ctx.moveTo(endX, endY)
      ctx.lineTo(
        endX - arrowLen * Math.cos(angle - 0.4),
        endY - arrowLen * Math.sin(angle - 0.4)
      )
      ctx.lineTo(
        endX - arrowLen * Math.cos(angle + 0.4),
        endY - arrowLen * Math.sin(angle + 0.4)
      )
      ctx.closePath()
      ctx.fillStyle = isOnPath ? "#3B82F6" : "#2D3A4F"
      ctx.fill()

      // Relationship label
      if (showRelationshipLabels && link.type) {
        const midX = (src.x + tgt.x) / 2
        const midY = (src.y! + tgt.y!) / 2
        const fontSize = Math.max(8 / globalScale, 1.5)
        ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"

        const text = link.type
        const metrics = ctx.measureText(text)
        const pad = 2 / globalScale
        ctx.fillStyle = "rgba(11,15,26,0.85)"
        ctx.fillRect(
          midX - metrics.width / 2 - pad,
          midY - fontSize / 2 - pad,
          metrics.width + pad * 2,
          fontSize + pad * 2
        )
        ctx.fillStyle = "#94A3B8"
        ctx.globalAlpha = 0.8
        ctx.fillText(text, midX, midY)
      }

      ctx.globalAlpha = 1.0
    },
    [showRelationshipLabels, highlightedPaths]
  )

  /* ---- Click handlers ---- */
  const handleNodeClick = useCallback(
    (node: FGNode, event: MouseEvent) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey) {
        addToSelection(node.key)
      } else {
        selectNodes([node.key])
      }
    },
    [selectNodes, addToSelection]
  )

  const handleBackgroundClick = useCallback(() => {
    if (isDragging.current) return
    selectNodes([])
    setDragStart(null)
    setDragEnd(null)
  }, [selectNodes])

  const handleNodeRightClick = useCallback(
    (node: FGNode, event: MouseEvent) => {
      event.preventDefault()
      openContextMenu({
        x: event.clientX,
        y: event.clientY,
        nodeKey: node.key,
        nodeLabel: node.label,
      })
    },
    [openContextMenu]
  )

  const handleNodeHover = useCallback(
    (node: FGNode | null) => setHoveredNode(node?.key ?? null),
    []
  )

  /* ---- Box/marquee selection pointer handlers ---- */
  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (selectionMode !== "drag") return
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      setDragStart({ x, y })
      setDragEnd({ x, y })
      isDragging.current = false
    },
    [selectionMode]
  )

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (selectionMode !== "drag" || !dragStart) return
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      isDragging.current = true
      setDragEnd({ x, y })
    },
    [selectionMode, dragStart]
  )

  const handlePointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (selectionMode !== "drag" || !dragStart) return
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const endX = e.clientX - rect.left
      const endY = e.clientY - rect.top

      // Micro-drag guard: skip if drag < 5px
      const dx = Math.abs(endX - dragStart.x)
      const dy = Math.abs(endY - dragStart.y)
      if (dx < 5 && dy < 5) {
        setDragStart(null)
        setDragEnd(null)
        isDragging.current = false
        return
      }

      const fg = fgRef.current
      if (!fg) {
        setDragStart(null)
        setDragEnd(null)
        isDragging.current = false
        return
      }

      // Convert screen corners to graph coordinates
      const topLeft = fg.screen2GraphCoords(
        Math.min(dragStart.x, endX),
        Math.min(dragStart.y, endY)
      )
      const bottomRight = fg.screen2GraphCoords(
        Math.max(dragStart.x, endX),
        Math.max(dragStart.y, endY)
      )

      const minGX = topLeft.x
      const maxGX = bottomRight.x
      const minGY = topLeft.y
      const maxGY = bottomRight.y

      const selected = fgData.nodes
        .filter((n) => {
          const nx = n.x ?? 0
          const ny = n.y ?? 0
          return nx >= minGX && nx <= maxGX && ny >= minGY && ny <= maxGY
        })
        .map((n) => n.key)

      if (selected.length > 0) selectNodes(selected)

      setDragStart(null)
      setDragEnd(null)
      isDragging.current = false
    },
    [selectionMode, dragStart, fgData.nodes, selectNodes, fgRef]
  )

  /* ---- Node drag to pin ---- */
  const handleNodeDragEnd = useCallback(
    (node: FGNode) => {
      // Pin node at its current position
      node.fx = node.x
      node.fy = node.y
      useGraphStore.getState().pinNode(node.key)
    },
    []
  )

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full bg-slate-950"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <ForceGraph2D
        ref={fgRef as any}
        graphData={fgData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="#0B0F1A"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node: FGNode, color, ctx) => {
          const sz = 4 + Math.min((node._degree ?? 0) * 0.8, 12)
          ctx.beginPath()
          ctx.arc(node.x ?? 0, node.y ?? 0, sz + 3, 0, 2 * Math.PI)
          ctx.fillStyle = color
          ctx.fill()
        }}
        linkCanvasObject={paintLink}
        onNodeClick={handleNodeClick}
        onNodeRightClick={handleNodeRightClick}
        onNodeHover={handleNodeHover}
        onNodeDragEnd={handleNodeDragEnd}
        onBackgroundClick={handleBackgroundClick}
        onEngineStop={handleEngineStop}
        enableNodeDrag={selectionMode === "click"}
        enablePanInteraction={selectionMode !== "drag"}
        cooldownTime={3000}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
      />

      {/* Drag selection rectangle overlay */}
      {selectionMode === "drag" && dragStart && dragEnd && isDragging.current && (
        <div
          className="pointer-events-none absolute border border-blue-500/50 bg-blue-500/10"
          style={{
            left: Math.min(dragStart.x, dragEnd.x),
            top: Math.min(dragStart.y, dragEnd.y),
            width: Math.abs(dragEnd.x - dragStart.x),
            height: Math.abs(dragEnd.y - dragStart.y),
          }}
        />
      )}

      {/* Stats overlay */}
      <div className="absolute bottom-3 left-3 rounded-md bg-slate-900/80 px-2 py-1 text-[10px] text-slate-400">
        {fgData.nodes.length} nodes · {fgData.links.length} edges
        {hiddenNodeKeys.size > 0 && ` · ${hiddenNodeKeys.size} hidden`}
      </div>
    </div>
  )
}
