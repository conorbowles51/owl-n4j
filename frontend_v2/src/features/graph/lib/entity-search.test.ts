import { describe, expect, it } from "vitest"
import type { GraphNode } from "@/types/graph.types"
import { applyNodeSearch, buildEntityFuse } from "./entity-search"

const nodes: GraphNode[] = [
  { key: "1", label: "Jonathan Smith", aliases: ["Jon"], type: "Person", properties: {} },
  { key: "2", label: "Dublin Office", type: "Location", properties: { owner: "Jonathan" } },
  { key: "3", label: "Alice Jones", type: "Person", properties: {} },
]

describe("entity search", () => {
  it("uses deterministic structured matching in filter mode", () => {
    const result = applyNodeSearch(nodes, "Jon NOT Alice", "filter", buildEntityFuse(nodes))
    expect(result.map((node) => node.key)).toEqual(["1", "2"])
  })

  it("supports one-character submitted searches deterministically", () => {
    const result = applyNodeSearch(nodes, "D", "search", buildEntityFuse(nodes))
    expect(result.map((node) => node.key)).toEqual(["2"])
  })

  it("uses ranked typo-tolerant matching in search mode", () => {
    const result = applyNodeSearch(nodes, "Jonathn", "search", buildEntityFuse(nodes))
    expect(result[0].key).toBe("1")
    expect(result.map((node) => node.key)).toContain("2")
  })
})

