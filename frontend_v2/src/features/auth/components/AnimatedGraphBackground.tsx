import { useEffect, useRef } from "react"
import { useTheme } from "@/lib/theme-provider"
import { nodeColors } from "@/lib/theme"

/* ── Fake investigation data ── */

interface GraphNode {
  name: string
  color: string
  hx: number // home x (0-1)
  hy: number // home y (0-1)
  radius: number // node circle radius
  phase: number
  freqX: number
  freqY: number
}

interface GraphEdge {
  from: number
  to: number
  label: string
}

// Nodes clustered closer together (0.2–0.85 x, 0.15–0.85 y), varied radii
const NODES: GraphNode[] = [
  { name: "James Harmon", color: nodeColors.person, hx: 0.20, hy: 0.18, radius: 5, phase: 0.0, freqX: 0.06, freqY: 0.08 },
  { name: "Nexus Corp", color: nodeColors.organization, hx: 0.38, hy: 0.14, radius: 7, phase: 1.2, freqX: 0.05, freqY: 0.07 },
  { name: "Transfer #4491", color: nodeColors.financial, hx: 0.55, hy: 0.20, radius: 4, phase: 2.4, freqX: 0.07, freqY: 0.05 },
  { name: "Maria Chen", color: nodeColors.person, hx: 0.72, hy: 0.16, radius: 6, phase: 0.8, freqX: 0.06, freqY: 0.09 },
  { name: "Warehouse 7B", color: nodeColors.location, hx: 0.22, hy: 0.38, radius: 4, phase: 3.1, freqX: 0.05, freqY: 0.06 },
  { name: "Invoice #2287", color: nodeColors.document, hx: 0.42, hy: 0.32, radius: 3, phase: 1.8, freqX: 0.08, freqY: 0.04 },
  { name: "Apex Holdings", color: nodeColors.organization, hx: 0.62, hy: 0.36, radius: 8, phase: 4.2, freqX: 0.04, freqY: 0.07 },
  { name: "Call 03/14", color: nodeColors.communication, hx: 0.80, hy: 0.34, radius: 3, phase: 0.5, freqX: 0.07, freqY: 0.05 },
  { name: "David Ortiz", color: nodeColors.person, hx: 0.25, hy: 0.55, radius: 5, phase: 2.0, freqX: 0.06, freqY: 0.07 },
  { name: "Shell Account", color: nodeColors.financial, hx: 0.40, hy: 0.50, radius: 6, phase: 5.0, freqX: 0.05, freqY: 0.09 },
  { name: "Server #DC-04", color: nodeColors.digital, hx: 0.55, hy: 0.52, radius: 4, phase: 1.5, freqX: 0.08, freqY: 0.04 },
  { name: "Meeting 11/02", color: nodeColors.event, hx: 0.70, hy: 0.50, radius: 5, phase: 3.7, freqX: 0.04, freqY: 0.06 },
  { name: "BMW X5 Black", color: nodeColors.vehicle, hx: 0.28, hy: 0.72, radius: 4, phase: 4.8, freqX: 0.06, freqY: 0.05 },
  { name: "Port Authority", color: nodeColors.location, hx: 0.48, hy: 0.68, radius: 7, phase: 0.3, freqX: 0.07, freqY: 0.08 },
  { name: "Email Chain", color: nodeColors.communication, hx: 0.65, hy: 0.70, radius: 3, phase: 2.9, freqX: 0.09, freqY: 0.06 },
  { name: "Evidence #118", color: nodeColors.evidence, hx: 0.82, hy: 0.65, radius: 5, phase: 1.0, freqX: 0.05, freqY: 0.07 },
  { name: "Sarah Wells", color: nodeColors.person, hx: 0.52, hy: 0.82, radius: 6, phase: 3.5, freqX: 0.06, freqY: 0.04 },
  { name: "Deposit #8830", color: nodeColors.financial, hx: 0.75, hy: 0.82, radius: 4, phase: 5.5, freqX: 0.05, freqY: 0.08 },
]

const EDGES: GraphEdge[] = [
  { from: 0, to: 1, label: "WORKS_AT" },
  { from: 0, to: 4, label: "VISITED" },
  { from: 1, to: 2, label: "INITIATED" },
  { from: 1, to: 6, label: "SUBSIDIARY_OF" },
  { from: 2, to: 3, label: "TRANSFERRED_TO" },
  { from: 3, to: 7, label: "CONTACTED" },
  { from: 4, to: 8, label: "OBSERVED_AT" },
  { from: 5, to: 1, label: "ISSUED_BY" },
  { from: 5, to: 9, label: "REFERENCES" },
  { from: 6, to: 10, label: "OWNS" },
  { from: 6, to: 11, label: "ORGANIZED" },
  { from: 7, to: 14, label: "FOLLOWED_BY" },
  { from: 8, to: 12, label: "DRIVES" },
  { from: 8, to: 9, label: "CONTROLS" },
  { from: 9, to: 2, label: "LINKED_TO" },
  { from: 10, to: 14, label: "STORED_ON" },
  { from: 11, to: 3, label: "ATTENDED_BY" },
  { from: 12, to: 13, label: "LOCATED_AT" },
  { from: 13, to: 16, label: "EMPLOYED" },
  { from: 14, to: 15, label: "SUPPORTS" },
  { from: 16, to: 17, label: "DEPOSITED" },
  { from: 17, to: 6, label: "RECEIVED_BY" },
]

const AMPLITUDE = 0.012
const TWO_PI = Math.PI * 2

// Left-to-right opacity gradient: x=0 → 0.15, x=1 → 1.0
function xFade(nx: number): number {
  return 0.15 + 0.85 * nx
}

/* ── Component ── */

export function AnimatedGraphBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { theme } = useTheme()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const parent = canvas.parentElement!
    const ctx = canvas.getContext("2d")!
    let raf = 0

    const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)

    const baseOpacity = {
      edgeLine: isDark ? 0.18 : 0.14,
      edgeLabel: isDark ? 0.10 : 0.07,
      nodeCircle: isDark ? 0.35 : 0.28,
      nodeName: isDark ? 0.18 : 0.13,
    }

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches

    function resize() {
      const dpr = window.devicePixelRatio || 1
      const w = parent.clientWidth
      const h = parent.clientHeight
      canvas!.width = w * dpr
      canvas!.height = h * dpr
      canvas!.style.width = `${w}px`
      canvas!.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const ro = new ResizeObserver(resize)
    ro.observe(parent)
    resize()

    function draw(t: number) {
      const w = parent.clientWidth
      const h = parent.clientHeight
      ctx.clearRect(0, 0, w, h)

      const sec = prefersReduced ? 0 : t / 1000

      const positions: Array<[number, number]> = new Array(NODES.length)
      for (let i = 0; i < NODES.length; i++) {
        const n = NODES[i]
        const x = (n.hx + AMPLITUDE * Math.sin(TWO_PI * n.freqX * sec + n.phase)) * w
        const y = (n.hy + AMPLITUDE * Math.cos(TWO_PI * n.freqY * sec + n.phase * 1.3)) * h
        positions[i] = [x, y]
      }

      // Draw edges
      ctx.lineWidth = 1
      for (let i = 0; i < EDGES.length; i++) {
        const e = EDGES[i]
        const [x1, y1] = positions[e.from]
        const [x2, y2] = positions[e.to]
        const mx = (x1 + x2) / 2
        const my = (y1 + y2) / 2
        const fade = xFade(mx / w)

        ctx.strokeStyle = isDark
          ? `rgba(148,163,184,${baseOpacity.edgeLine * fade})`
          : `rgba(71,85,105,${baseOpacity.edgeLine * fade})`
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()

        ctx.font = "9px ui-monospace, monospace"
        ctx.fillStyle = isDark
          ? `rgba(148,163,184,${baseOpacity.edgeLabel * fade})`
          : `rgba(71,85,105,${baseOpacity.edgeLabel * fade})`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillText(e.label, mx, my)
      }

      // Draw nodes
      for (let i = 0; i < NODES.length; i++) {
        const n = NODES[i]
        const [x, y] = positions[i]
        const fade = xFade(x / w)

        ctx.globalAlpha = baseOpacity.nodeCircle * fade
        ctx.fillStyle = n.color
        ctx.beginPath()
        ctx.arc(x, y, n.radius, 0, TWO_PI)
        ctx.fill()

        ctx.globalAlpha = baseOpacity.nodeName * fade
        ctx.fillStyle = isDark ? "#CBD5E1" : "#334155"
        ctx.font = "10px ui-sans-serif, system-ui, sans-serif"
        ctx.textAlign = "center"
        ctx.textBaseline = "top"
        ctx.fillText(n.name, x, y + n.radius + 3)

        ctx.globalAlpha = 1
      }

      if (!prefersReduced) {
        raf = requestAnimationFrame(draw)
      }
    }

    if (prefersReduced) {
      draw(0)
    } else {
      raf = requestAnimationFrame(draw)
    }

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [theme])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0"
      aria-hidden="true"
    />
  )
}
