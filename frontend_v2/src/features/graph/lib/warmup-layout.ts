import { forceCenter, forceLink, forceManyBody, forceSimulation, type LinkForce, type StrengthForce } from "d3-force-3d"

export interface WarmupNode {
  id: string
  fx?: number
  fy?: number
}

export interface WarmupLink {
  source: string
  target: string
}

export interface WarmupParams {
  ticks: number
  alphaDecay: number
  velocityDecay: number
  linkDistance: number
  chargeStrength: number
  centerStrength: number
}

interface SimNode extends WarmupNode {
  x?: number
  y?: number
  vx?: number
  vy?: number
}

/**
 * The graph canvas's warm-up layout steps, run where they are called (the layout worker).
 *
 * Built the way react-force-graph-2d builds its own simulation (link, charge and center forces, two
 * dimensions, heated to alpha 1, links resolved by node id) with the canvas's force settings, then
 * stepped `ticks` times. Returns x, y, vx, vy for each node, in node order, four numbers per node.
 */
export function warmupLayout(nodes: WarmupNode[], links: WarmupLink[], params: WarmupParams): Float64Array {
  const simNodes: SimNode[] = nodes.map((n) => ({ ...n }))
  const simLinks = links.map((l) => ({ source: l.source, target: l.target }))
  const simulation = forceSimulation<SimNode>()
    .force("link", forceLink())
    .force("charge", forceManyBody())
    .force("center", forceCenter())
    .stop()
  simulation.alphaDecay(params.alphaDecay).velocityDecay(params.velocityDecay)
  simulation.force<LinkForce<SimNode, unknown>>("link")?.distance(params.linkDistance)
  simulation.force<StrengthForce>("charge")?.strength(params.chargeStrength)
  simulation.force<StrengthForce>("center")?.strength(params.centerStrength)
  simulation.alpha(1).nodes(simNodes)
  simulation.force<LinkForce<SimNode, unknown>>("link")?.id((d) => d.id).links(simLinks)
  for (let i = 0; i < params.ticks; i++) simulation.tick()

  const out = new Float64Array(simNodes.length * 4)
  simNodes.forEach((n, i) => {
    out[i * 4] = n.x ?? 0
    out[i * 4 + 1] = n.y ?? 0
    out[i * 4 + 2] = n.vx ?? 0
    out[i * 4 + 3] = n.vy ?? 0
  })
  return out
}
