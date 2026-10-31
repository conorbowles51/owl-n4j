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

/** What the layout worker posts: positions after `step` steps; `done` on the last message. */
export interface LayoutMessage {
  positions: Float64Array
  step: number
  done: boolean
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
 *
 * `onStep` is called before the first step (step 0, the starting positions) and after every step, with a
 * function that copies the positions at that moment in the same layout. Reading them does not change
 * the steps, so the result is the same with or without it.
 */
export function warmupLayout(
  nodes: WarmupNode[],
  links: WarmupLink[],
  params: WarmupParams,
  onStep?: (step: number, read: () => Float64Array) => void,
): Float64Array {
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
  const read = () => readPositions(simNodes)
  onStep?.(0, read)
  for (let i = 0; i < params.ticks; i++) {
    simulation.tick()
    onStep?.(i + 1, read)
  }
  return read()
}

function readPositions(simNodes: SimNode[]): Float64Array {
  const out = new Float64Array(simNodes.length * 4)
  simNodes.forEach((n, i) => {
    out[i * 4] = n.x ?? 0
    out[i * 4 + 1] = n.y ?? 0
    out[i * 4 + 2] = n.vx ?? 0
    out[i * 4 + 3] = n.vy ?? 0
  })
  return out
}
