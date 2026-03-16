import { useRef, useEffect, useCallback, useMemo, useState } from "react"
import ForceGraph2D, {
  type ForceGraphMethods,
  type NodeObject,
  type LinkObject,
} from "react-force-graph-2d"
import { useGraphStore } from "@/stores/graph.store"
import { getNodeColor, communityColors, getCanvasColors } from "@/lib/theme"
import { useTheme } from "@/lib/theme-provider"
import type { GraphData, CommunityOverview } from "@/types/graph.types"

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
  /* Super-node fields */
  _isSuperNode?: boolean
  _memberCount?: number
  _entityTypeBreakdown?: Record<string, number>
  _internalEdgeCount?: number
}

interface FGLink extends LinkObject {
  type: string
  weight?: number
  _edgeCount?: number
  _edgeTypes?: string[]
}

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface GraphCanvasProps {
  data: GraphData
  caseId: string
  graphRef?: React.MutableRefObject<ForceGraphMethods | undefined>
  communityOverview?: CommunityOverview | null
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function GraphCanvas({ data, graphRef: externalRef, communityOverview }: GraphCanvasProps) {
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
    viewMode,
    expandedCommunities,
    expandCommunity,
    collapseCommunity,
  } = useGraphStore()

  const { theme } = useTheme()
  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)
  const canvasColors = getCanvasColors(isDark)

  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  /* ---- Drag selection state ---- */
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [dragEnd, setDragEnd] = useState<{ x: number; y: number } | null>(null)
  const isDraggingRef = useRef(false)
  const [isDraggingState, setIsDraggingState] = useState(false)

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

  /* ---- Build force-graph data with degree calc + community view ---- */
  const fgData = useMemo(() => {
    /* ---- Community overview mode ---- */
    if (viewMode === "community-overview" && communityOverview) {
      const nodes: FGNode[] = []
      const links: FGLink[] = []
      const expandedSet = expandedCommunities

      // Degree counts for expanded nodes (needed for sizing)
      const degreeCounts = new Map<string, number>()
      for (const e of data.edges) {
        degreeCounts.set(e.source, (degreeCounts.get(e.source) ?? 0) + 1)
        degreeCounts.set(e.target, (degreeCounts.get(e.target) ?? 0) + 1)
      }

      for (const sn of communityOverview.super_nodes) {
        if (expandedSet.has(sn.community_id)) {
          // Expanded: show individual nodes from cached lightweight data
          const memberKeys = new Set<string>()
          for (const [key, cid] of Object.entries(communityOverview.node_community_map)) {
            if (cid === sn.community_id) memberKeys.add(key)
          }

          for (const n of data.nodes) {
            if (memberKeys.has(n.key) && !hiddenNodeKeys.has(n.key)) {
              nodes.push({
                id: n.key,
                key: n.key,
                label: n.label,
                type: n.type,
                confidence: n.confidence,
                community_id: sn.community_id,
                mentioned: n.mentioned,
                _degree: degreeCounts.get(n.key) ?? 0,
              })
            }
          }

          // Include intra-community edges
          for (const e of data.edges) {
            if (memberKeys.has(e.source) && memberKeys.has(e.target)) {
              links.push({
                source: e.source,
                target: e.target,
                type: e.type,
                weight: e.weight,
              })
            }
          }
        } else {
          // Collapsed: render as super-node
          nodes.push({
            id: `community_${sn.community_id}`,
            key: `community_${sn.community_id}`,
            label: sn.label,
            type: "community",
            community_id: sn.community_id,
            _degree: 0,
            _isSuperNode: true,
            _memberCount: sn.member_count,
            _entityTypeBreakdown: sn.entity_type_breakdown,
            _internalEdgeCount: sn.internal_edge_count,
          })
        }
      }

      // Cross-community edges
      for (const ce of communityOverview.cross_community_edges) {
        const srcExpanded = expandedSet.has(ce.source_community)
        const tgtExpanded = expandedSet.has(ce.target_community)

        if (!srcExpanded && !tgtExpanded) {
          // Both collapsed — super-node to super-node
          links.push({
            source: `community_${ce.source_community}`,
            target: `community_${ce.target_community}`,
            type: ce.edge_types.join(", "),
            _edgeCount: ce.edge_count,
            _edgeTypes: ce.edge_types,
          })
        } else if (srcExpanded && tgtExpanded) {
          // Both expanded — add actual edges between communities from cached data
          const srcKeys = new Set<string>()
          const tgtKeys = new Set<string>()
          for (const [key, cid] of Object.entries(communityOverview.node_community_map)) {
            if (cid === ce.source_community) srcKeys.add(key)
            if (cid === ce.target_community) tgtKeys.add(key)
          }
          for (const e of data.edges) {
            if (
              (srcKeys.has(e.source) && tgtKeys.has(e.target)) ||
              (tgtKeys.has(e.source) && srcKeys.has(e.target))
            ) {
              links.push({ source: e.source, target: e.target, type: e.type, weight: e.weight })
            }
          }
        } else {
          // One expanded, one collapsed — connect expanded nodes to super-node
          const expandedCid = srcExpanded ? ce.source_community : ce.target_community
          const collapsedCid = srcExpanded ? ce.target_community : ce.source_community
          const expandedKeys = new Set<string>()
          for (const [key, cid] of Object.entries(communityOverview.node_community_map)) {
            if (cid === expandedCid) expandedKeys.add(key)
          }
          // Find which expanded nodes connect to the collapsed community
          const collapsedKeys = new Set<string>()
          for (const [key, cid] of Object.entries(communityOverview.node_community_map)) {
            if (cid === collapsedCid) collapsedKeys.add(key)
          }
          const bridgeNodes = new Set<string>()
          for (const e of data.edges) {
            if (expandedKeys.has(e.source) && collapsedKeys.has(e.target)) bridgeNodes.add(e.source)
            if (expandedKeys.has(e.target) && collapsedKeys.has(e.source)) bridgeNodes.add(e.target)
          }
          // Connect top bridge node (or first) to the super-node
          const bridgeArr = Array.from(bridgeNodes)
          if (bridgeArr.length > 0) {
            links.push({
              source: bridgeArr[0],
              target: `community_${collapsedCid}`,
              type: ce.edge_types.join(", "),
              _edgeCount: ce.edge_count,
            })
          }
        }
      }

      return { nodes, links }
    }

    /* ---- Full / default mode ---- */
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
  }, [data, hiddenNodeKeys, pinnedNodeKeys, viewMode, communityOverview, expandedCommunities])

  /* ---- Adaptive force simulation tuning ---- */
  const nodeCount = fgData.nodes.length
  const isLargeGraph = nodeCount > 500
  const simAlphaDecay = isLargeGraph ? 0.05 : 0.02
  const simVelocityDecay = isLargeGraph ? 0.5 : 0.3
  const simCooldownTime = isLargeGraph ? 1500 : 3000
  const simWarmupTicks = isLargeGraph ? 50 : 0

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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fgData.nodes.length])

  /* ---- Node color logic ---- */
  const getColor = useCallback(
    (node: FGNode): string => {
      if (node._isSuperNode) {
        return communityColors[(node.community_id ?? 0) % communityColors.length]
      }
      if (communityMap?.has(node.key)) {
        const cid = communityMap.get(node.key)!
        return communityColors[cid % communityColors.length]
      }
      // In community-overview with expanded communities, color by community
      if (viewMode === "community-overview" && node.community_id != null) {
        return communityColors[node.community_id % communityColors.length]
      }
      return getNodeColor(node.type)
    },
    [communityMap, viewMode]
  )

  /* ---- Custom node renderer with LOD tiers ---- */
  const paintNode = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0
      const y = node.y ?? 0

      /* ---- Super-node rendering ---- */
      if (node._isSuperNode) {
        const memberCount = node._memberCount ?? 1
        const radius = Math.log(memberCount + 1) * 8
        const color = getColor(node)

        // Outer glow ring
        ctx.beginPath()
        ctx.arc(x, y, radius + 3, 0, 2 * Math.PI)
        ctx.fillStyle = color.replace(")", ",0.15)").replace("rgb", "rgba")
        ctx.fill()

        // Double-border hint (indicates expandable)
        ctx.beginPath()
        ctx.arc(x, y, radius + 1.5, 0, 2 * Math.PI)
        ctx.strokeStyle = color
        ctx.lineWidth = 1 / globalScale
        ctx.globalAlpha = 0.5
        ctx.stroke()
        ctx.globalAlpha = 1.0

        // Main circle
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, 2 * Math.PI)
        ctx.fillStyle = color
        ctx.fill()

        // Pie chart of entity type breakdown (if enough space)
        if (globalScale > 0.3 && node._entityTypeBreakdown) {
          const breakdown = node._entityTypeBreakdown
          const total = Object.values(breakdown).reduce((a, b) => a + b, 0)
          if (total > 0) {
            let startAngle = -Math.PI / 2
            const pieRadius = radius * 0.65
            for (const [type, count] of Object.entries(breakdown)) {
              const sliceAngle = (count / total) * 2 * Math.PI
              ctx.beginPath()
              ctx.moveTo(x, y)
              ctx.arc(x, y, pieRadius, startAngle, startAngle + sliceAngle)
              ctx.closePath()
              ctx.fillStyle = getNodeColor(type)
              ctx.globalAlpha = 0.7
              ctx.fill()
              startAngle += sliceAngle
            }
            ctx.globalAlpha = 1.0
          }
        }

        // Member count badge
        const badgeFontSize = Math.max(10 / globalScale, 3)
        ctx.font = `bold ${badgeFontSize}px Inter, system-ui, sans-serif`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillStyle = "#fff"
        ctx.fillText(String(memberCount), x, y)

        // Label
        if (globalScale > 0.3) {
          const labelFontSize = Math.max(10 / globalScale, 2)
          ctx.font = `${labelFontSize}px Inter, system-ui, sans-serif`
          ctx.textAlign = "center"
          ctx.textBaseline = "top"
          ctx.fillStyle = canvasColors.labelText
          const label = node.label.length > 30 ? node.label.slice(0, 28) + "..." : node.label
          ctx.fillText(label, x, y + radius + 3)
        }

        // Selection ring
        if (selectedNodeKeys.has(node.key)) {
          ctx.beginPath()
          ctx.arc(x, y, radius + 4, 0, 2 * Math.PI)
          ctx.strokeStyle = "#3B82F6"
          ctx.lineWidth = 2.5 / globalScale
          ctx.stroke()
        }

        return
      }

      /* ---- Regular node rendering with LOD ---- */
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

      /* LOD: Dots tier (globalScale < 0.3) — circle only */
      if (globalScale < 0.3) {
        ctx.beginPath()
        ctx.arc(x, y, sz, 0, 2 * Math.PI)
        ctx.fillStyle = color
        ctx.fill()

        // Still show selection ring even at low zoom
        if (isSelected) {
          ctx.beginPath()
          ctx.arc(x, y, sz + 2.5, 0, 2 * Math.PI)
          ctx.strokeStyle = "#3B82F6"
          ctx.lineWidth = 2 / globalScale
          ctx.stroke()
        }

        ctx.globalAlpha = 1.0
        return
      }

      /* LOD: Compact tier (globalScale 0.3–1.0) — circle + selective labels */
      if (globalScale < 1.0) {
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

        // Node circle
        ctx.beginPath()
        ctx.arc(x, y, sz, 0, 2 * Math.PI)
        ctx.fillStyle = color
        ctx.fill()

        // Label only for high-degree, selected, or hovered nodes
        const showLabel = (node._degree ?? 0) > 5 || isSelected || isHovered
        if (showLabel) {
          const fontSize = Math.max(10 / globalScale, 2)
          ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
          ctx.textAlign = "center"
          ctx.textBaseline = "top"
          ctx.fillStyle = canvasColors.labelText
          const label = node.label.length > 20 ? node.label.slice(0, 18) + "..." : node.label
          ctx.fillText(label, x, y + sz + 2)
        }

        ctx.globalAlpha = 1.0
        return
      }

      /* LOD: Full tier (globalScale >= 1.0) — everything */

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
        ctx.strokeStyle = canvasColors.hoverStroke
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
      ctx.fillStyle = canvasColors.labelText
      const label =
        node.label.length > 20
          ? node.label.slice(0, 18) + "..."
          : node.label
      ctx.fillText(label, x, y + sz + 2)

      ctx.globalAlpha = 1.0
    },
    [selectedNodeKeys, hoveredNode, getColor, analysisHighlight, highlightedPaths, canvasColors]
  )

  /* ---- Custom link renderer with LOD tiers ---- */
  const paintLink = useCallback(
    (link: FGLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const src = link.source as FGNode
      const tgt = link.target as FGNode
      if (!src?.x || !tgt?.x) return

      /* LOD: skip links entirely at very low zoom */
      if (globalScale < 0.3) return

      const isOnPath =
        highlightedPaths?.has((src as FGNode).key) &&
        highlightedPaths?.has((tgt as FGNode).key)

      const isCrossComm = (link._edgeCount ?? 0) > 0

      const baseWidth = isCrossComm
        ? Math.log((link._edgeCount ?? 1) + 1) * 1.5
        : Math.max(0.5, (link.weight ?? 1) * 0.8)
      const width = baseWidth / Math.sqrt(globalScale)

      ctx.beginPath()
      ctx.moveTo(src.x, src.y!)
      ctx.lineTo(tgt.x, tgt.y!)
      ctx.strokeStyle = isOnPath ? "#3B82F6" : canvasColors.linkColor
      ctx.lineWidth = isOnPath ? width * 2 : width
      ctx.globalAlpha = isOnPath ? 0.9 : isCrossComm ? 0.6 : 0.4
      ctx.stroke()

      /* LOD: Thin lines only (globalScale 0.3–0.6) — no arrows, no labels */
      if (globalScale < 0.6) {
        ctx.globalAlpha = 1.0
        return
      }

      /* Full detail (globalScale >= 0.6) — arrows + labels */

      // Arrowhead
      const dx = tgt.x - src.x
      const dy = tgt.y! - src.y!
      const len = Math.sqrt(dx * dx + dy * dy)
      if (len < 1) {
        ctx.globalAlpha = 1.0
        return
      }

      const tgtSz = (tgt as FGNode)._isSuperNode
        ? Math.log(((tgt as FGNode)._memberCount ?? 1) + 1) * 8
        : 4 + Math.min(((tgt as FGNode)._degree ?? 0) * 0.8, 12)
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
      ctx.fillStyle = isOnPath ? "#3B82F6" : canvasColors.linkColor
      ctx.fill()

      // Cross-community edge count label
      if (isCrossComm && link._edgeCount && link._edgeCount > 1) {
        const midX = (src.x + tgt.x) / 2
        const midY = (src.y! + tgt.y!) / 2
        const countFontSize = Math.max(8 / globalScale, 1.5)
        ctx.font = `bold ${countFontSize}px Inter, system-ui, sans-serif`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        const text = `${link._edgeCount}`
        const metrics = ctx.measureText(text)
        const pad = 2 / globalScale
        ctx.fillStyle = canvasColors.labelBg
        ctx.fillRect(
          midX - metrics.width / 2 - pad,
          midY - countFontSize / 2 - pad,
          metrics.width + pad * 2,
          countFontSize + pad * 2
        )
        ctx.fillStyle = canvasColors.labelText
        ctx.globalAlpha = 0.9
        ctx.fillText(text, midX, midY)
      }

      // Relationship label
      if (showRelationshipLabels && link.type && !isCrossComm) {
        const midX = (src.x + tgt.x) / 2
        const midY = (src.y! + tgt.y!) / 2
        const fontSize = Math.max(8 / globalScale, 1.5)
        ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
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
      }

      ctx.globalAlpha = 1.0
    },
    [showRelationshipLabels, highlightedPaths, canvasColors]
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

  /* ---- Double-click: expand super-node ---- */
  const lastClickRef = useRef<{ key: string; time: number } | null>(null)
  const handleNodeClickWithDblClick = useCallback(
    (node: FGNode, event: MouseEvent) => {
      const now = Date.now()
      const last = lastClickRef.current

      if (last && last.key === node.key && now - last.time < 400) {
        // Double-click detected
        lastClickRef.current = null
        if (node._isSuperNode && node.community_id != null) {
          expandCommunity(node.community_id)
          return
        }
      } else {
        lastClickRef.current = { key: node.key, time: now }
      }

      handleNodeClick(node, event)
    },
    [handleNodeClick, expandCommunity]
  )

  const handleBackgroundClick = useCallback(() => {
    if (isDraggingRef.current) return
    selectNodes([])
    setDragStart(null)
    setDragEnd(null)
  }, [selectNodes])

  const handleNodeRightClick = useCallback(
    (node: FGNode, event: MouseEvent) => {
      event.preventDefault()

      // If right-clicking an expanded community node, offer collapse
      if (
        viewMode === "community-overview" &&
        !node._isSuperNode &&
        node.community_id != null &&
        expandedCommunities.has(node.community_id)
      ) {
        openContextMenu({
          x: event.clientX,
          y: event.clientY,
          nodeKey: node.key,
          nodeLabel: node.label,
        })
        // Store the community_id for collapse action
        ;(window as Record<string, unknown>).__collapseCommunityId = node.community_id
        return
      }

      openContextMenu({
        x: event.clientX,
        y: event.clientY,
        nodeKey: node.key,
        nodeLabel: node.label,
      })
    },
    [openContextMenu, viewMode, expandedCommunities]
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
      isDraggingRef.current = false
      setIsDraggingState(false)
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
      isDraggingRef.current = true
      setIsDraggingState(true)
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
        isDraggingRef.current = false
        setIsDraggingState(false)
        return
      }

      const fg = fgRef.current
      if (!fg) {
        setDragStart(null)
        setDragEnd(null)
        isDraggingRef.current = false
        setIsDraggingState(false)
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
      isDraggingRef.current = false
      setIsDraggingState(false)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectionMode, dragStart, fgData.nodes, selectNodes]
  )

  /* ---- Node drag to pin ---- */
  const handleNodeDragEnd = useCallback(
    (node: FGNode) => {
      if (node._isSuperNode) return // Don't pin super-nodes
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
      className="relative h-full w-full bg-slate-100 dark:bg-slate-950"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <ForceGraph2D
        ref={fgRef as React.MutableRefObject<ForceGraphMethods<FGNode, FGLink>>}
        graphData={fgData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor={canvasColors.background}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node: FGNode, color, ctx) => {
          const sz = node._isSuperNode
            ? Math.log((node._memberCount ?? 1) + 1) * 8
            : 4 + Math.min((node._degree ?? 0) * 0.8, 12)
          ctx.beginPath()
          ctx.arc(node.x ?? 0, node.y ?? 0, sz + 3, 0, 2 * Math.PI)
          ctx.fillStyle = color
          ctx.fill()
        }}
        linkCanvasObject={paintLink}
        onNodeClick={handleNodeClickWithDblClick}
        onNodeRightClick={handleNodeRightClick}
        onNodeHover={handleNodeHover}
        onNodeDragEnd={handleNodeDragEnd}
        onBackgroundClick={handleBackgroundClick}
        onEngineStop={handleEngineStop}
        enableNodeDrag={selectionMode === "click"}
        enablePanInteraction={selectionMode !== "drag"}
        cooldownTime={simCooldownTime}
        d3AlphaDecay={simAlphaDecay}
        d3VelocityDecay={simVelocityDecay}
        warmupTicks={simWarmupTicks}
      />

      {/* Drag selection rectangle overlay */}
      {selectionMode === "drag" && dragStart && dragEnd && isDraggingState && (
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
      <div className="absolute bottom-3 left-3 rounded-md bg-slate-100/90 dark:bg-slate-900/80 px-2 py-1 text-[10px] text-slate-500 dark:text-slate-400">
        {fgData.nodes.length} nodes · {fgData.links.length} edges
        {hiddenNodeKeys.size > 0 && ` · ${hiddenNodeKeys.size} hidden`}
        {viewMode === "community-overview" && communityOverview && (
          <> · {communityOverview.total_nodes} total ({communityOverview.community_count} communities)</>
        )}
      </div>
    </div>
  )
}
