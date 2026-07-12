import { renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"
import type { GraphData } from "@/types/graph.types"
import { useGraphStore } from "@/stores/graph.store"
import { useGraphSearch } from "./use-graph-search"

const data: GraphData = {
  nodes: [
    { key: "p1", label: "Alice", type: "Person", properties: {} },
    { key: "p2", label: "Bob", type: "Person", properties: {} },
    { key: "l1", label: "Dublin", type: "Location", properties: {} },
  ],
  edges: [
    { source: "p1", target: "p2", type: "KNOWS" },
    { source: "p1", target: "l1", type: "LOCATED_AT" },
  ],
}

describe("useGraphSearch", () => {
  beforeEach(() => {
    useGraphStore.setState({
      searchMode: "filter",
      searchDraft: "",
      appliedSearchQuery: "",
      filters: {},
    })
  })

  it("combines text and entity-type filters and prunes orphaned edges", () => {
    useGraphStore.setState({ appliedSearchQuery: "Ali OR Dublin", filters: { Person: true } })
    const { result } = renderHook(() => useGraphSearch(data))
    expect(result.current.filteredData?.nodes.map((node) => node.key)).toEqual(["p1"])
    expect(result.current.filteredData?.edges).toEqual([])
    expect(result.current.filteredNodes).toBe(1)
    expect(result.current.totalNodes).toBe(3)
  })

  it("restores all nodes and edges after clearing", () => {
    useGraphStore.setState({ appliedSearchQuery: "Alice" })
    useGraphStore.getState().clearSearch()
    const { result } = renderHook(() => useGraphSearch(data))
    expect(result.current.filteredData).toEqual(data)
  })
})

