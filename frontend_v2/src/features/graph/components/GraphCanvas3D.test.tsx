import { act, render, waitFor } from "@testing-library/react"
import { StrictMode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphData } from "@/types/graph.types"
import { GraphCanvas3D } from "./GraphCanvas3D"

interface MockGraphNode {
  key: string
  label: string
  _degree: number
}

interface MockForceGraphProps {
  graphData?: { nodes: MockGraphNode[] }
  nodeThreeObject?: (node: MockGraphNode) => unknown
  nodeThreeObjectExtend?: boolean
  onEngineTick?: () => void
  onNodeHover?: (node: MockGraphNode | null) => void
}

interface MockNodeLabel {
  fontFace: string
  material: { depthTest: boolean }
  renderOrder: number
}

const graphMocks = vi.hoisted(() => ({
  latestProps: null as MockForceGraphProps | null,
  d3Force: vi.fn(),
  reheat: vi.fn(),
  refresh: vi.fn(),
}))

vi.mock("three-spritetext", () => ({
  default: class MockSpriteText {
    center = { y: 0.5 }
    material = { depthTest: true }
    renderOrder = 0
    fontFace = ""
    fontSize = 0
    fontWeight = ""
    strokeWidth = 0
    strokeColor = ""
    text: string
    textHeight: number
    color: string

    constructor(text: string, textHeight: number, color: string) {
      this.text = text
      this.textHeight = textHeight
      this.color = color
    }
  },
}))

vi.mock("react-force-graph-3d", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  const force = {
    distance: vi.fn(),
    strength: vi.fn(),
  }

  graphMocks.d3Force.mockReturnValue(force)

  return {
    default: React.forwardRef(function MockForceGraph3D(
      props: MockForceGraphProps,
      ref: React.ForwardedRef<unknown>
    ) {
      React.useEffect(() => {
        graphMocks.latestProps = props
      }, [props])
      React.useImperativeHandle(ref, () => ({
        d3Force: graphMocks.d3Force,
        d3ReheatSimulation: graphMocks.reheat,
        refresh: graphMocks.refresh,
      }))
      return React.createElement("div", { "data-testid": "force-graph-3d" })
    }),
  }
})

const graphData: GraphData = {
  nodes: [
    { key: "alpha", label: "Alpha", type: "person", properties: {} },
    { key: "bravo", label: "Bravo", type: "organization", properties: {} },
  ],
  edges: [{ source: "alpha", target: "bravo", type: "KNOWS" }],
}

function makeGraphData(nodeCount: number): GraphData {
  return {
    nodes: Array.from({ length: nodeCount }, (_, index) => ({
      key: `node-${index.toString().padStart(3, "0")}`,
      label: `Node ${index.toString().padStart(3, "0")}`,
      type: "person",
      properties: {},
    })),
    edges: Array.from({ length: nodeCount - 1 }, (_, index) => ({
      source: `node-${index.toString().padStart(3, "0")}`,
      target: `node-${(index + 1).toString().padStart(3, "0")}`,
      type: "CONNECTED_TO",
    })),
  }
}

describe("GraphCanvas3D", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      }
    )
    graphMocks.latestProps = null
    graphMocks.d3Force.mockClear()
    graphMocks.reheat.mockClear()
    graphMocks.refresh.mockClear()
    useGraphStore.setState({
      linkDistance: 200,
      chargeStrength: -50,
      centerStrength: 0.4,
      selectedNodeKeys: new Set(),
      hiddenNodeKeys: new Set(),
      pinnedNodeKeys: new Set(),
    })
  })

  it("waits for the force layout to tick before reheating across remounts", async () => {
    const firstRender = render(
      <StrictMode>
        <GraphCanvas3D data={graphData} />
      </StrictMode>
    )

    expect(graphMocks.d3Force).toHaveBeenCalled()
    expect(graphMocks.reheat).not.toHaveBeenCalled()

    firstRender.unmount()
    render(
      <StrictMode>
        <GraphCanvas3D data={graphData} />
      </StrictMode>
    )

    expect(graphMocks.reheat).not.toHaveBeenCalled()

    act(() => graphMocks.latestProps?.onEngineTick?.())
    act(() => useGraphStore.getState().setLinkDistance(240))

    await waitFor(() => expect(graphMocks.reheat).toHaveBeenCalledTimes(1))
  })

  it("labels the 200 most connected main nodes and every Spotlight node", async () => {
    const largeGraph = makeGraphData(201)
    const mainRender = render(<GraphCanvas3D data={largeGraph} />)

    const mainProps = graphMocks.latestProps
    expect(mainProps?.nodeThreeObjectExtend).toBe(true)
    const labelledMainNodes =
      mainProps?.graphData?.nodes.filter((node) =>
        mainProps.nodeThreeObject?.(node)
      ) ?? []
    expect(labelledMainNodes).toHaveLength(200)
    const firstLabel = mainProps?.nodeThreeObject?.(
      labelledMainNodes[0]
    ) as MockNodeLabel
    expect(firstLabel.fontFace).toBe('"Source Sans 3", system-ui, sans-serif')
    expect(firstLabel.material.depthTest).toBe(false)
    expect(firstLabel.renderOrder).toBe(1)

    const unlabelledNode = mainProps?.graphData?.nodes.find(
      (node) => !mainProps.nodeThreeObject?.(node)
    )
    expect(unlabelledNode).toBeDefined()

    act(() => useGraphStore.getState().selectNodes([unlabelledNode!.key]))
    await waitFor(() =>
      expect(
        graphMocks.latestProps?.nodeThreeObject?.(unlabelledNode!)
      ).toBeDefined()
    )

    mainRender.unmount()
    render(<GraphCanvas3D data={largeGraph} variant="spotlight" />)

    const spotlightProps = graphMocks.latestProps
    const labelledSpotlightNodes =
      spotlightProps?.graphData?.nodes.filter((node) =>
        spotlightProps.nodeThreeObject?.(node)
      ) ?? []
    expect(labelledSpotlightNodes).toHaveLength(201)
  })
})
