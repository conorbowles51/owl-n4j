import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react"
import ForceGraph3D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-3d"
import SpriteText from "three-spritetext"
import { getCanvasColors, getNodeColor } from "@/lib/theme"
import { useTheme } from "@/lib/theme-context"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphData } from "@/types/graph.types"

interface FGNode {
  id: string
  key: string
  label: string
  type: string
  confidence?: number
  community_id?: number
  mentioned?: boolean
  _degree: number
}

interface FGLink {
  source: string
  target: string
  type: string
  weight?: number
}

type ForceNode = NodeObject<FGNode>
type ForceLink = LinkObject<FGNode, FGLink>

const MAX_VISIBLE_LABELS = 200
const MAX_LABEL_CHARACTERS = 32

interface GraphCanvas3DProps {
  data: GraphData
  graphRef?: MutableRefObject<ForceGraphMethods | undefined>
  variant?: "main" | "spotlight"
}

function escapeTooltip(value: string) {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[character] ?? character
  )
}

function endpointKey(endpoint: string | number | ForceNode | undefined) {
  if (endpoint == null) return ""
  if (typeof endpoint === "object")
    return endpoint.key ?? String(endpoint.id ?? "")
  return String(endpoint)
}

function displayLabel(label: string) {
  return label.length > MAX_LABEL_CHARACTERS
    ? `${label.slice(0, MAX_LABEL_CHARACTERS - 1)}…`
    : label
}

export function GraphCanvas3D({
  data,
  graphRef: externalRef,
  variant = "main",
}: GraphCanvas3DProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const internalRef = useRef<ForceGraphMethods<FGNode, FGLink> | undefined>(
    undefined
  )
  const fgRef =
    (externalRef as MutableRefObject<
      ForceGraphMethods<FGNode, FGLink> | undefined
    >) ?? internalRef
  const [pinnedPositions, setPinnedPositions] = useState(
    () => new Map<string, { x: number; y: number; z: number }>()
  )
  const hasZoomedToFit = useRef(false)
  const layoutReady = useRef(false)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const isSpotlight = variant === "spotlight"

  const selectedNodeKeys = useGraphStore((state) => state.selectedNodeKeys)
  const selectNodes = useGraphStore((state) => state.selectNodes)
  const addToSelection = useGraphStore((state) => state.addToSelection)
  const hiddenNodeKeys = useGraphStore((state) => state.hiddenNodeKeys)
  const pinnedNodeKeys = useGraphStore((state) => state.pinnedNodeKeys)
  const pinNode = useGraphStore((state) => state.pinNode)
  const linkDistance = useGraphStore((state) => state.linkDistance)
  const chargeStrength = useGraphStore((state) => state.chargeStrength)
  const centerStrength = useGraphStore((state) => state.centerStrength)
  const showRelationshipLabels = useGraphStore(
    (state) => state.showRelationshipLabels
  )
  const openContextMenu = useGraphStore((state) => state.openContextMenu)

  const { theme } = useTheme()
  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)
  const canvasColors = getCanvasColors(isDark)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (width > 0 && height > 0) setDimensions({ width, height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const fgData = useMemo(() => {
    const visibleNodes = isSpotlight
      ? data.nodes
      : data.nodes.filter((node) => !hiddenNodeKeys.has(node.key))
    const visibleKeys = new Set(visibleNodes.map((node) => node.key))
    const degreeCounts = new Map<string, number>()

    for (const edge of data.edges) {
      if (!visibleKeys.has(edge.source) || !visibleKeys.has(edge.target))
        continue
      degreeCounts.set(edge.source, (degreeCounts.get(edge.source) ?? 0) + 1)
      degreeCounts.set(edge.target, (degreeCounts.get(edge.target) ?? 0) + 1)
    }

    const nodes: ForceNode[] = visibleNodes.map((node) => {
      const pinnedPosition = pinnedPositions.get(node.key)
      const isPinned = !isSpotlight && pinnedNodeKeys.has(node.key)
      return {
        id: node.key,
        key: node.key,
        label: node.label,
        type: node.type,
        confidence: node.confidence,
        community_id: node.community_id,
        mentioned: node.mentioned,
        _degree: degreeCounts.get(node.key) ?? 0,
        ...(isPinned && pinnedPosition
          ? {
              fx: pinnedPosition.x,
              fy: pinnedPosition.y,
              fz: pinnedPosition.z,
            }
          : {}),
      }
    })

    const links: ForceLink[] = data.edges
      .filter(
        (edge) => visibleKeys.has(edge.source) && visibleKeys.has(edge.target)
      )
      .map((edge) => ({
        source: edge.source,
        target: edge.target,
        type: edge.type,
        weight: edge.weight,
      }))

    return { nodes, links }
  }, [data, hiddenNodeKeys, isSpotlight, pinnedNodeKeys, pinnedPositions])

  const nodeCount = fgData.nodes.length
  const isLargeGraph = nodeCount > 500
  const labelledNodeKeys = useMemo(() => {
    if (isSpotlight || nodeCount <= MAX_VISIBLE_LABELS) {
      return new Set(fgData.nodes.map((node) => node.key))
    }

    const keys = new Set(
      [...fgData.nodes]
        .sort(
          (a, b) =>
            b._degree - a._degree ||
            a.label.localeCompare(b.label) ||
            a.key.localeCompare(b.key)
        )
        .slice(0, MAX_VISIBLE_LABELS)
        .map((node) => node.key)
    )

    for (const key of selectedNodeKeys) keys.add(key)
    if (hoveredNode) keys.add(hoveredNode)
    return keys
  }, [fgData.nodes, hoveredNode, isSpotlight, nodeCount, selectedNodeKeys])

  const createNodeLabel = useCallback(
    (node: ForceNode) => {
      if (!labelledNodeKeys.has(node.key)) {
        // 3d-force-graph treats a falsy result as "use only the default node",
        // though its React declaration currently excludes that documented case.
        return undefined as unknown as SpriteText
      }

      const sprite = new SpriteText(
        displayLabel(node.label),
        isSpotlight ? 12 : 6,
        canvasColors.labelText
      )
      sprite.fontFace = '"Source Sans 3", system-ui, sans-serif'
      sprite.fontSize = 72
      sprite.fontWeight = selectedNodeKeys.has(node.key) ? "600" : "500"
      sprite.strokeWidth = 0.12
      sprite.strokeColor = canvasColors.background
      sprite.center.y = -0.6
      sprite.material.depthTest = false
      sprite.renderOrder = 1
      return sprite
    },
    [
      canvasColors.background,
      canvasColors.labelText,
      isSpotlight,
      labelledNodeKeys,
      selectedNodeKeys,
    ]
  )

  const activeLink = useCallback(
    (link: ForceLink) =>
      selectedNodeKeys.has(endpointKey(link.source)) ||
      selectedNodeKeys.has(endpointKey(link.target)),
    [selectedNodeKeys]
  )

  useEffect(() => {
    const graph = fgRef.current
    if (!graph) return
    const distance = isSpotlight ? Math.min(linkDistance, 100) : linkDistance
    const charge = isSpotlight ? Math.min(chargeStrength, -100) : chargeStrength
    graph.d3Force("link")?.distance(distance)
    graph.d3Force("charge")?.strength(charge)
    graph.d3Force("center")?.strength(centerStrength)
    // graphData starts the initial simulation itself. Reheating before its
    // first tick races the library's deferred layout initialization on remount.
    if (layoutReady.current) graph.d3ReheatSimulation()
  }, [centerStrength, chargeStrength, fgRef, isSpotlight, linkDistance])

  useEffect(() => {
    fgRef.current?.refresh()
  }, [fgRef, hoveredNode, selectedNodeKeys])

  useEffect(() => {
    hasZoomedToFit.current = false
  }, [data])

  const handleEngineStop = () => {
    if (hasZoomedToFit.current || !fgRef.current || fgData.nodes.length === 0)
      return
    hasZoomedToFit.current = true
    fgRef.current.zoomToFit(500, isSpotlight ? 30 : 60)
  }

  const handleEngineTick = useCallback(() => {
    layoutReady.current = true
  }, [])

  const handleNodeClick = useCallback(
    (node: ForceNode, event: MouseEvent) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey) {
        addToSelection(node.key)
      } else {
        selectNodes([node.key])
      }
    },
    [addToSelection, selectNodes]
  )

  const handleNodeRightClick = useCallback(
    (node: ForceNode, event: MouseEvent) => {
      if (isSpotlight) return
      event.preventDefault()
      if (!selectedNodeKeys.has(node.key)) addToSelection(node.key)
      openContextMenu({
        x: event.clientX,
        y: event.clientY,
        nodeKey: node.key,
        nodeLabel: node.label,
      })
    },
    [addToSelection, isSpotlight, openContextMenu, selectedNodeKeys]
  )

  const handleNodeDragEnd = useCallback(
    (node: ForceNode) => {
      if (isSpotlight || node.x == null || node.y == null || node.z == null)
        return
      const position = { x: node.x, y: node.y, z: node.z }
      setPinnedPositions((current) => {
        const next = new Map(current)
        next.set(node.key, position)
        return next
      })
      node.fx = position.x
      node.fy = position.y
      node.fz = position.z
      pinNode(node.key)
    },
    [isSpotlight, pinNode]
  )

  return (
    <div ref={containerRef} className="relative h-full w-full bg-slate-950">
      <ForceGraph3D
        ref={fgRef}
        graphData={fgData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor={canvasColors.background}
        showNavInfo={!isSpotlight}
        controlType="orbit"
        nodeLabel={(node: ForceNode) => escapeTooltip(node.label)}
        nodeColor={(node: ForceNode) =>
          selectedNodeKeys.has(node.key) || hoveredNode === node.key
            ? canvasColors.selectionStroke
            : getNodeColor(node.type)
        }
        nodeVal={(node: ForceNode) => {
          const degreeScale = 1 + Math.min(node._degree, 30) * 0.12
          const confidenceScale =
            node.confidence == null ? 1 : 0.8 + node.confidence * 0.6
          const interactionScale = selectedNodeKeys.has(node.key)
            ? 2.2
            : hoveredNode === node.key
              ? 1.65
              : 1
          return degreeScale * confidenceScale * interactionScale
        }}
        nodeRelSize={isSpotlight ? 4.5 : 4}
        nodeOpacity={0.92}
        nodeResolution={isLargeGraph ? 4 : 8}
        nodeThreeObject={createNodeLabel}
        nodeThreeObjectExtend
        linkLabel={(link: ForceLink) =>
          showRelationshipLabels ? escapeTooltip(link.type) : ""
        }
        linkColor={(link: ForceLink) =>
          activeLink(link)
            ? canvasColors.selectionStroke
            : canvasColors.linkColor
        }
        linkWidth={(link: ForceLink) => (activeLink(link) ? 1.25 : 0)}
        linkOpacity={selectedNodeKeys.size > 0 ? 0.22 : 0.34}
        linkDirectionalArrowLength={(link: ForceLink) =>
          activeLink(link) ? 3 : 0
        }
        linkDirectionalArrowColor={() => canvasColors.selectionStroke}
        onNodeClick={handleNodeClick}
        onNodeRightClick={isSpotlight ? undefined : handleNodeRightClick}
        onNodeHover={(node: ForceNode | null) =>
          setHoveredNode(node?.key ?? null)
        }
        onNodeDragEnd={handleNodeDragEnd}
        onBackgroundClick={() => selectNodes([])}
        onEngineTick={handleEngineTick}
        onEngineStop={handleEngineStop}
        cooldownTime={isLargeGraph ? 1800 : isSpotlight ? 2000 : 3000}
        warmupTicks={isLargeGraph ? 40 : 0}
        d3AlphaDecay={isLargeGraph ? 0.05 : 0.02}
        d3VelocityDecay={isLargeGraph ? 0.5 : 0.3}
      />

      {!isSpotlight ? (
        <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-slate-100/90 px-2 py-1 text-[10px] text-slate-500 dark:bg-slate-900/80 dark:text-slate-400">
          {fgData.nodes.length} nodes · {fgData.links.length} edges · 3D
          {hiddenNodeKeys.size > 0 ? ` · ${hiddenNodeKeys.size} hidden` : ""}
        </div>
      ) : null}
    </div>
  )
}
