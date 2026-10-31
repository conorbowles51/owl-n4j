import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphData } from "@/types/graph.types"
import { warmupLayout, type WarmupLink, type WarmupNode, type WarmupParams } from "../lib/warmup-layout"
import { GraphCanvas } from "./GraphCanvas"

interface MockNode {
  key: string
  x?: number
  y?: number
}

interface MockProps {
  graphData: { nodes: MockNode[]; links: unknown[] }
  warmupTicks?: number
}

const mocks = vi.hoisted(() => ({ props: [] as MockProps[] }))

vi.mock("react-force-graph-2d", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  const force = { distance: vi.fn(), strength: vi.fn() }
  return {
    default: React.forwardRef(function MockForceGraph2D(props: MockProps, ref: React.ForwardedRef<unknown>) {
      mocks.props.push(props)
      React.useImperativeHandle(ref, () => ({
        d3Force: () => force,
        d3ReheatSimulation: vi.fn(),
        zoomToFit: vi.fn(),
      }))
      return React.createElement("div", { "data-testid": "force-graph-2d" })
    }),
  }
})

// A worker that answers with the real warm-up function, as the layout worker does.
class FakeLayoutWorker {
  static created = 0
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  constructor() {
    FakeLayoutWorker.created++
  }
  postMessage(data: { nodes: WarmupNode[]; links: WarmupLink[]; params: WarmupParams }) {
    const positions = warmupLayout(data.nodes, data.links, data.params)
    setTimeout(() => this.onmessage?.({ data: { positions } } as MessageEvent), 0)
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
    FakeLayoutWorker.created = 0
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} })
    useGraphStore.setState({
      linkDistance: 200, chargeStrength: -50, centerStrength: 0.4,
      selectedNodeKeys: new Set(), hiddenNodeKeys: new Set(), pinnedNodeKeys: new Set(),
    })
  })
  afterEach(() => vi.unstubAllGlobals())

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
})
