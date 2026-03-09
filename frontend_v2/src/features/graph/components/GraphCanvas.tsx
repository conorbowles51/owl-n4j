import { useRef, useEffect, useCallback } from "react"
import { useGraphStore } from "@/stores/graph.store"
import { nodeColors } from "@/lib/theme"
import type { GraphData } from "@/types/graph.types"
import type { EntityType } from "@/lib/theme"

interface GraphCanvasProps {
  data: GraphData
  caseId: string
}

export function GraphCanvas({ data }: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { selectNodes, addToSelection } = useGraphStore()

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      // Simple click handling - find nearest node
      const canvas = canvasRef.current
      if (!canvas) return

      const rect = canvas.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top

      // Find nearest node (simple distance check)
      let closestNode: string | null = null
      let closestDist = 20 // click radius in pixels

      for (const node of data.nodes) {
        const nx = (node.x ?? 0) * 1 + canvas.width / 2
        const ny = (node.y ?? 0) * 1 + canvas.height / 2
        const dist = Math.sqrt((x - nx) ** 2 + (y - ny) ** 2)
        if (dist < closestDist) {
          closestDist = dist
          closestNode = node.key
        }
      }

      if (closestNode) {
        if (e.ctrlKey || e.metaKey) {
          addToSelection(closestNode)
        } else {
          selectNodes([closestNode])
        }
      } else {
        selectNodes([])
      }
    },
    [data.nodes, selectNodes, addToSelection]
  )

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Set canvas size
    const parent = canvas.parentElement
    if (parent) {
      canvas.width = parent.clientWidth
      canvas.height = parent.clientHeight
    }

    // Clear
    ctx.fillStyle = "#0B0F1A"
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const cx = canvas.width / 2
    const cy = canvas.height / 2

    // Simple force-directed layout (positions from data or circular fallback)
    const positions = data.nodes.map((node, i) => {
      if (node.x !== undefined && node.y !== undefined) {
        return { x: node.x + cx, y: node.y + cy }
      }
      const angle = (2 * Math.PI * i) / data.nodes.length
      const radius = Math.min(canvas.width, canvas.height) * 0.35
      return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) }
    })

    // Draw edges
    ctx.strokeStyle = "#2D3A4F"
    ctx.lineWidth = 1
    for (const edge of data.edges) {
      const si = data.nodes.findIndex((n) => n.key === edge.source)
      const ti = data.nodes.findIndex((n) => n.key === edge.target)
      if (si >= 0 && ti >= 0) {
        ctx.beginPath()
        ctx.moveTo(positions[si].x, positions[si].y)
        ctx.lineTo(positions[ti].x, positions[ti].y)
        ctx.stroke()
      }
    }

    // Draw nodes
    for (let i = 0; i < data.nodes.length; i++) {
      const node = data.nodes[i]
      const pos = positions[i]
      const color = nodeColors[node.type as EntityType] ?? "#8494A7"

      ctx.beginPath()
      ctx.arc(pos.x, pos.y, 6, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()

      // Label
      ctx.fillStyle = "#AAB7C7"
      ctx.font = "10px Inter, sans-serif"
      ctx.textAlign = "center"
      ctx.fillText(node.label, pos.x, pos.y + 16)
    }
  }, [data])

  return (
    <div className="relative h-full w-full bg-slate-950">
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        onClick={handleClick}
      />
      <div className="absolute bottom-3 left-3 rounded-md bg-slate-900/80 px-2 py-1 text-[10px] text-slate-400">
        {data.nodes.length} nodes · {data.edges.length} edges
      </div>
    </div>
  )
}
