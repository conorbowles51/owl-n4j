import { describe, expect, it } from "vitest"
import { forceCenter, forceLink, forceManyBody, forceSimulation, type LinkForce, type StrengthForce } from "d3-force-3d"
import { warmupLayout, type WarmupParams } from "./warmup-layout"

const params: WarmupParams = {
  ticks: 50, alphaDecay: 0.05, velocityDecay: 0.5, linkDistance: 200, chargeStrength: -50, centerStrength: 0.4,
}

function fixture(count: number) {
  const nodes = Array.from({ length: count }, (_, i) => ({ id: `n${i}` }))
  const links = Array.from({ length: count - 1 }, (_, i) => ({ source: `n${i}`, target: `n${(i * 7 + 1) % count}` }))
  return { nodes, links }
}

describe("warmupLayout", () => {
  it("steps the simulation exactly as the canvas does: same forces, settings, order and step count", () => {
    const { nodes, links } = fixture(600)
    // react-force-graph-2d: a stopped simulation with link, charge and center forces; the decay props;
    // the canvas's force settings; then on new data stop, alpha 1, nodes, links by id, warm-up ticks
    type N = { id: string; x?: number; y?: number; vx?: number; vy?: number }
    const own = nodes.map((n) => ({ ...n })) as N[]
    const sim = forceSimulation<N>().force("link", forceLink()).force("charge", forceManyBody()).force("center", forceCenter()).stop()
    sim.alphaDecay(params.alphaDecay).velocityDecay(params.velocityDecay)
    sim.force<LinkForce<N, unknown>>("link")?.distance(params.linkDistance)
    sim.force<StrengthForce>("charge")?.strength(params.chargeStrength)
    sim.force<StrengthForce>("center")?.strength(params.centerStrength)
    sim.stop().alpha(1).nodes(own)
    sim.force<LinkForce<N, unknown>>("link")?.id((d) => d.id).links(links.map((l) => ({ ...l })))
    for (let i = 0; i < params.ticks; i++) sim.tick()

    const out = warmupLayout(nodes, links, params)
    expect(out.length).toBe(600 * 4)
    own.forEach((n, i) => {
      expect([out[i * 4], out[i * 4 + 1], out[i * 4 + 2], out[i * 4 + 3]]).toEqual([n.x, n.y, n.vx, n.vy])
    })
  })

  it("keeps pinned nodes where they were pinned and leaves the caller's objects alone", () => {
    const { nodes, links } = fixture(50)
    const input = nodes.map((n, i) => (i === 3 ? { ...n, fx: 12.5, fy: -40 } : n))
    const out = warmupLayout(input, links, params)
    expect([out[12], out[13]]).toEqual([12.5, -40])
    expect("x" in input[0]).toBe(false)
    expect(Number.isFinite(out[0]) && Number.isFinite(out[1])).toBe(true)
  })

  it("reports every step without changing the result", () => {
    const { nodes, links } = fixture(300)
    const plain = warmupLayout(nodes, links, params)
    const seen: number[] = []
    let atTen: Float64Array | null = null
    const reported = warmupLayout(nodes, links, params, (step, read) => {
      seen.push(step)
      if (step === 10) atTen = read()
    })
    expect(seen).toEqual(Array.from({ length: params.ticks + 1 }, (_, i) => i))
    expect(Array.from(reported)).toEqual(Array.from(plain))
    // a copy of the positions at that step: the ten-step layout, not the final one
    expect(Array.from(atTen!)).toEqual(Array.from(warmupLayout(nodes, links, { ...params, ticks: 10 })))
  })
})
