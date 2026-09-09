import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { countNodeSources, useFilteredSortedNodes } from "./use-filtered-sorted-nodes"
import type { GraphEdge, GraphNode } from "@/types/graph.types"

const nodes: GraphNode[] = [
  { key: "person-1", label: "Alice", type: "Person", properties: {} },
  { key: "location-1", label: "Dublin", type: "Location", properties: {} },
]

const edges: GraphEdge[] = []

function renderFilteredNodes(selectedTypes: Set<string> | null) {
  return renderHook(() => useFilteredSortedNodes({
    nodes,
    edges,
    searchTerm: "",
    selectedTypes,
    sortColumns: [],
    pageSize: 50,
    currentPage: 0,
  }))
}

describe("countNodeSources", () => {
  it("counts distinct source documents stored on graph properties", () => {
    const node = {
      key: "person-1",
      label: "Victoria Blackwood QC",
      type: "person",
      properties: {
        source_files: [
          "registry-supplement.pdf",
          "authorisation.pdf",
          "registry-supplement.pdf",
        ],
      },
    } as GraphNode

    expect(countNodeSources(node)).toBe(2)
  })
})

describe("useFilteredSortedNodes type selection", () => {
  it("distinguishes all, none, and one selected type", () => {
    const all = renderFilteredNodes(null)
    expect(all.result.current.filteredNodes).toHaveLength(2)

    const none = renderFilteredNodes(new Set())
    expect(none.result.current.filteredNodes).toEqual([])

    const one = renderFilteredNodes(new Set(["Person"]))
    expect(one.result.current.filteredNodes.map((node) => node.key)).toEqual(["person-1"])
  })
})
