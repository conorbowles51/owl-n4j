// The parts of d3-force-3d (the simulation react-force-graph-2d runs) that the graph layout worker uses.
declare module "d3-force-3d" {
  export interface SimulationNode {
    index?: number
    x?: number
    y?: number
    vx?: number
    vy?: number
    fx?: number | null
    fy?: number | null
  }
  export interface Force {
    (alpha: number): void
  }
  export interface LinkForce<N, L> extends Force {
    id(fn: (node: N) => string): LinkForce<N, L>
    links(links: L[]): LinkForce<N, L>
    distance(distance: number): LinkForce<N, L>
  }
  export interface StrengthForce extends Force {
    strength(strength: number): StrengthForce
  }
  export interface Simulation<N> {
    force(name: string, force: Force | null): Simulation<N>
    force<F extends Force>(name: string): F | undefined
    nodes(nodes: N[]): Simulation<N>
    alpha(alpha: number): Simulation<N>
    alpha(): number
    alphaDecay(decay: number): Simulation<N>
    velocityDecay(decay: number): Simulation<N>
    stop(): Simulation<N>
    tick(iterations?: number): Simulation<N>
  }
  export function forceSimulation<N extends SimulationNode>(nodes?: N[], numDimensions?: number): Simulation<N>
  export function forceLink<N, L>(links?: L[]): LinkForce<N, L>
  export function forceManyBody(): StrengthForce
  export function forceCenter(x?: number, y?: number): StrengthForce
}
