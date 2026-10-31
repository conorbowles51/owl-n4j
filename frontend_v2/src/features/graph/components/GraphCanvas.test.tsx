import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphData } from "@/types/graph.types"
import { warmupLayout, type LayoutMessage, type WarmupLink, type WarmupNode, type WarmupParams } from "../lib/warmup-layout"
import { GraphCanvas } from "./GraphCanvas"

interface MockNode {
  key: string
  x?: number
  y?: number
}

interface MockProps {
  graphData: { nodes: MockNode[]; links: unknown[] }
  warmupTicks?: number
  cooldownTicks?: number
  enableNodeDrag?: boolean
  onRenderFramePost?: () => void
}

const mocks = vi.hoisted(() => ({ props: [] as MockProps[], reheats: 0 }))

vi.mock("react-force-graph-2d", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  const force = { distance: vi.fn(), strength: vi.fn() }
  return {
    default: React.forwardRef(function MockForceGraph2D(props: MockProps, ref: React.ForwardedRef<unknown>) {
      mocks.props.push(props)
      React.useImperativeHandle(ref, () => ({
        d3Force: () => force,
        d3ReheatSimulation: () => {
          mocks.reheats++
        },
        zoomToFit: vi.fn(),
      }))
      return React.createElement("div", { "data-testid": "force-graph-2d" })
    }),
  }
})

// A worker that answers with the real warm-up function, as the layout worker does: the starting
// positions first, then the final ones.
class FakeLayoutWorker {
  static created = 0
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  constructor() {
    FakeLayoutWorker.created++
  }
  postMessage(data: { nodes: WarmupNode[]; links: WarmupLink[]; params: WarmupParams }) {
    const messages: LayoutMessage[] = []
    const positions = warmupLayout(data.nodes, data.links, data.params, (step, read) => {
      if (step === 0) messages.push({ positions: read(), step, done: false })
    })
    messages.push({ positions, step: data.params.ticks, done: true })
    messages.forEach((m, i) => setTimeout(() => this.onmessage?.({ data: m } as MessageEvent), i * 5))
  }
  terminate() {}
}

// A worker whose messages the test sends itself.
class ManualLayoutWorker {
  static last: ManualLayoutWorker | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  request: { nodes: WarmupNode[]; links: WarmupLink[]; params: WarmupParams } | null = null
  constructor() {
    ManualLayoutWorker.last = this
  }
  postMessage(data: { nodes: WarmupNode[]; links: WarmupLink[]; params: WarmupParams }) {
    this.request = data
  }
  send(message: LayoutMessage) {
    act(() => this.onmessage?.({ data: message } as MessageEvent))
  }
  terminate() {}
}

function makeGraph(count: number): GraphData {
  return {
    nodes: Array.from({ length: count }, (_, i) => ({ key: `n${i}`, label: `N ${i}`, type: "person", properties: {} })),
    edges: Array.from({ length: count - 1 }, (_, i) => ({ source: `n${i}`, target: `n${i + 1}`, type: "KNOWS" })),
  }
}

const last = () => mocks.props[mocks.props.length - 1]

describe("GraphCanvas layout", () => {
  beforeEach(() => {
    mocks.props = []
    mocks.reheats = 0
    FakeLayoutWorker.created = 0
    ManualLayoutWorker.last = null
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} })
    useGraphStore.setState({
      linkDistance: 200, chargeStrength: -50, centerStrength: 0.4,
      selectedNodeKeys: new Set(), hiddenNodeKeys: new Set(), pinnedNodeKeys: new Set(),
    })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("lays out a large graph in a worker and draws it without warming up on the page", async () => {
    vi.stubGlobal("Worker", FakeLayoutWorker)
    render(<GraphCanvas data={makeGraph(600)} caseId="case-1" />)

    // never handed all 600 nodes with warm-up steps to run on the page
    expect(mocks.props.some((p) => p.graphData.nodes.length === 600 && p.warmupTicks !== 0)).toBe(false)
    await waitFor(() => expect(last().graphData.nodes.length).toBe(600))
    expect(last().warmupTicks).toBe(0)
    expect(FakeLayoutWorker.created).toBeGreaterThan(0)
    expect(last().graphData.nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y))).toBe(true)
  })

  it("shows no stale graph while a changed large graph is laid out again", async () => {
    vi.stubGlobal("Worker", FakeLayoutWorker)
    const view = render(<GraphCanvas data={makeGraph(600)} caseId="case-1" />)
    await waitFor(() => expect(last().graphData.nodes.length).toBe(600))
    mocks.props = []
    view.rerender(<GraphCanvas data={makeGraph(700)} caseId="case-2" />)
    // the 600 nodes of the previous graph are never offered for clicks while the 700 are arranged
    expect(mocks.props[0].graphData.nodes.length).toBe(0)
    await waitFor(() => expect(last().graphData.nodes.length).toBe(700))
    expect(mocks.props.some((p) => p.graphData.nodes.length === 600)).toBe(false)
  })

  it("warms up on the page, as before, when no worker can be started", async () => {
    vi.stubGlobal("Worker", class { constructor() { throw new Error("no workers") } })
    render(<GraphCanvas data={makeGraph(600)} caseId="case-1" />)
    await waitFor(() => expect(last().graphData.nodes.length).toBe(600))
    expect(last().warmupTicks).toBe(50)
  })

  it("draws a small graph at once, with no worker", async () => {
    vi.stubGlobal("Worker", FakeLayoutWorker)
    await act(async () => {
      render(<GraphCanvas data={makeGraph(20)} caseId="case-1" />)
    })
    expect(mocks.props[0].graphData.nodes.length).toBe(20)
    expect(last().warmupTicks).toBe(0)
    expect(FakeLayoutWorker.created).toBe(0)
  })

  it("draws the graph while the worker arranges it, without layout steps or dragging on the page", async () => {
    vi.stubGlobal("Worker", ManualLayoutWorker)
    vi.spyOn(performance, "now").mockReturnValue(1000) // drawings take no time: every set is drawn
    render(<GraphCanvas data={makeGraph(600)} caseId="case-1" />)
    const worker = ManualLayoutWorker.last!
    const { nodes, links, params } = worker.request!
    const steps: Float64Array[] = []
    const final = warmupLayout(nodes, links, params, (step, read) => {
      if (step === 0 || step === 20) steps.push(read())
    })
    expect(last().graphData.nodes.length).toBe(0)

    worker.send({ positions: steps[0], step: 0, done: false })
    expect(last().graphData.nodes.length).toBe(600)
    expect(last().cooldownTicks).toBe(0) // drawn, never stepped on the page
    expect(last().warmupTicks).toBe(0)
    expect(last().enableNodeDrag).toBe(false)
    expect(last().graphData.nodes[5].x).toBe(steps[0][20])

    const shown = last().graphData
    act(() => last().onRenderFramePost?.()) // the first positions are drawn
    const reheatsBefore = mocks.reheats
    worker.send({ positions: steps[1], step: 20, done: false })
    expect(last().graphData).toBe(shown) // same graph, positions moved in place
    expect(shown.nodes[5].x).toBe(steps[1][20])
    expect(mocks.reheats).toBeGreaterThan(reheatsBefore) // asks the canvas to draw them
    expect(last().cooldownTicks).toBe(0)

    worker.send({ positions: final.slice(), step: 50, done: true })
    expect(last().graphData).toBe(shown)
    expect(last().cooldownTicks).toBe(Infinity) // the canvas settles from here, as a fresh graph does
    expect(last().enableNodeDrag).toBe(true)
    shown.nodes.forEach((n, i) => {
      expect([n.x, n.y]).toEqual([final[i * 4], final[i * 4 + 1]])
    })
  })

  it("starts the canvas afresh, warming up on the page, when the worker fails after drawing", async () => {
    vi.stubGlobal("Worker", ManualLayoutWorker)
    render(<GraphCanvas data={makeGraph(600)} caseId="case-1" />)
    const worker = ManualLayoutWorker.last!
    const { nodes, links, params } = worker.request!
    let start: Float64Array | null = null
    warmupLayout(nodes, links, { ...params, ticks: 0 }, (_, read) => {
      start = read()
    })
    worker.send({ positions: start!, step: 0, done: false })
    const shown = last().graphData
    act(() => worker.onerror?.())
    expect(last().graphData).not.toBe(shown) // a new graph object: the canvas lays it out again
    expect(last().graphData.nodes.length).toBe(600)
    expect(last().warmupTicks).toBe(50)
    expect(last().cooldownTicks).toBe(Infinity)
    expect(last().graphData.nodes.every((n) => n.x === undefined)).toBe(true)
  })

  it("draws positions in between only when the page has had four times the last drawing free", async () => {
    vi.stubGlobal("Worker", ManualLayoutWorker)
    let now = 1000
    const clock = vi.spyOn(performance, "now").mockImplementation(() => now)
    try {
      render(<GraphCanvas data={makeGraph(600)} caseId="case-1" />)
      const worker = ManualLayoutWorker.last!
      const { nodes, links, params } = worker.request!
      const sets: Float64Array[] = []
      const final = warmupLayout(nodes, links, params, (step, read) => {
        if (step === 0 || step === 10 || step === 20 || step === 30) sets.push(read())
      })
      const frame = () => act(() => last().onRenderFramePost?.())

      let reheats = mocks.reheats
      worker.send({ positions: sets[0], step: 0, done: false })
      expect(mocks.reheats).toBe(reheats + 1) // the first positions are always drawn
      reheats = mocks.reheats

      now += 500 // a frame while the drawing is still under way: nothing new is asked
      worker.send({ positions: sets[1], step: 10, done: false })
      expect(mocks.reheats).toBe(reheats)
      expect(last().graphData.nodes[5].x).toBe(sets[1][20]) // but the positions are written

      now += 1500
      frame() // that drawing took 2 s
      now += 1000 // 1 s free: less than 4 x 2 s, not drawn
      worker.send({ positions: sets[2], step: 20, done: false })
      expect(mocks.reheats).toBe(reheats)

      now += 7000 // 8 s free since the drawing ended
      worker.send({ positions: sets[3], step: 30, done: false })
      expect(mocks.reheats).toBe(reheats + 1)
      reheats = mocks.reheats

      now += 100 // the final positions are always drawn, even while a drawing is under way
      worker.send({ positions: final.slice(), step: 50, done: true })
      expect(mocks.reheats).toBe(reheats + 1)
      expect(last().cooldownTicks).toBe(Infinity)
      last().graphData.nodes.forEach((n, i) => {
        expect([n.x, n.y]).toEqual([final[i * 4], final[i * 4 + 1]])
      })
    } finally {
      clock.mockRestore()
    }
  })
})
