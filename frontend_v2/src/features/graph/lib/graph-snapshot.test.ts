import { describe, expect, it } from "vitest"
import type { GraphData } from "@/types/graph.types"
import { buildSnapshotSubgraph, normaliseLinks, readCanvasGraph, registerCanvasGraphSource } from "./graph-snapshot"

const shown: GraphData = {
  nodes: [
    { key: "p1", label: "Jane Roe", type: "Person", properties: { source_files: ["bank.pdf"], big: "x".repeat(10) } },
    { key: "e1", label: "Wire", type: "Transaction", properties: {} },
    { key: "h1", label: "Hidden", type: "Person", properties: {} },
  ],
  edges: [
    { source: "p1", target: "e1", type: "SENT" },
    { source: "p1", target: "h1", type: "KNOWS" },
  ],
}

describe("snapshot of the graph on screen (BUG-009: nothing could save a snapshot)", () => {
  it("keeps only what the canvas shows, where each node sits, and each entity's source files", () => {
    const canvas = {
      nodes: [{ key: "p1", x: 10, y: -5 }, { key: "e1", x: 40, y: 12 }],
      links: [{ source: "p1", target: "e1", type: "SENT" }],
    }
    const out = buildSnapshotSubgraph(shown, canvas)
    expect(out.positions).toBe("canvas")
    expect(out.nodes.map((n) => n.key)).toEqual(["p1", "e1"])
    expect(out.nodes[0]).toMatchObject({ x: 10, y: -5, properties: { source_files: ["bank.pdf"] } })
    expect(out.nodes[0].properties).not.toHaveProperty("big")
    expect(out.nodes[0].color).toMatch(/^#/)
    expect(out.links).toEqual([{ source: "p1", target: "e1", type: "SENT" }])
  })

  it("falls back to the shown graph without positions when there is no 2D canvas", () => {
    const out = buildSnapshotSubgraph(shown, null)
    expect(out.positions).toBe("none")
    expect(out.nodes).toHaveLength(3)
    expect(out.nodes[0]).not.toHaveProperty("x")
    expect(out.links).toHaveLength(2)
  })

  it("reads links the layout turned into node objects, and unregisters cleanly", () => {
    expect(normaliseLinks([{ source: { key: "a" }, target: { id: "b" }, type: "T" }])).toEqual([{ source: "a", target: "b", type: "T" }])
    const off = registerCanvasGraphSource(() => ({ nodes: [], links: [] }))
    expect(readCanvasGraph()).toEqual({ nodes: [], links: [] })
    off()
    expect(readCanvasGraph()).toBeNull()
  })
})
