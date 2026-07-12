import { describe, expect, it } from "vitest"
import type { GraphNode } from "@/types/graph.types"
import { matchesSearchQuery, parseSearchQuery } from "./search-query"

const node: GraphNode = {
  key: "person-1",
  label: "John Smith",
  aliases: ["Johnny"],
  type: "Person",
  summary: "Lives in Dublin",
  notes: "Met Alice",
  properties: { age: 42, active: true, tags: ["witness"] },
}

const matches = (query: string) => matchesSearchQuery(parseSearchQuery(query), node)

describe("search query", () => {
  it("supports implicit and explicit AND", () => {
    expect(matches("John Dublin")).toBe(true)
    expect(matches("John AND Belfast")).toBe(false)
  })

  it("applies NOT before AND and AND before OR", () => {
    expect(matches("Belfast OR John AND Dublin")).toBe(true)
    expect(matches("John NOT Alice")).toBe(false)
    expect(matches("John -Belfast")).toBe(true)
  })

  it("supports quoted phrases and wildcards", () => {
    expect(matches('"john smith"')).toBe(true)
    expect(matches("Jo*n Sm?th")).toBe(true)
    expect(matches('"Smith John"')).toBe(false)
  })

  it("matches keys, aliases, types, and primitive properties case-insensitively", () => {
    expect(matches("PERSON-1 AND johnny AND person AND 42 AND witness AND TRUE")).toBe(true)
  })

  it("handles incomplete expressions without throwing", () => {
    expect(() => parseSearchQuery('John OR NOT "')).not.toThrow()
    expect(matches("John AND")).toBe(true)
    expect(matches("NOT")).toBe(true)
  })
})

