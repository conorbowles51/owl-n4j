import { describe, expect, it } from "vitest"
import { EMPTY_SCOPE } from "@/features/phones/ui/scope"
import type { Scope } from "@/features/phones/ui/ScopeBar"
import type { GraphEdge, GraphNode } from "@/types/graph.types"
import { graphScopeKeys, graphScopeLimits } from "./phone-scope"

/** 07 4.5: Open in Graph with the scope carried, and a stated limit when the Graph cannot show all of it. */
const node = (key: string) => ({ key, label: key, type: "x" }) as GraphNode
const NODES = ["phone-extraction:p1", "phone-extraction:p2", "phone-identity:phone:+1", "phone-identity:phone:+2", "doc-1"].map(node)
const EDGES: GraphEdge[] = [
  { source: "phone-identity:phone:+1", target: "phone-extraction:p1", type: "APPEARS_ON" },
  { source: "phone-identity:phone:+2", target: "phone-extraction:p2", type: "APPEARS_ON" },
]
const P1 = { id: "p1", label: "C1", index: 0 }

describe("the Graph nodes of a scope", () => {
  it("takes the people, and only the ones on the Graph", () => {
    const scope: Scope = { ...EMPTY_SCOPE, people: [{ key: "phone:+1", label: "Ana" }, { key: "phone:+9", label: "Not drawn" }] }
    expect(graphScopeKeys(scope, NODES, EDGES)).toEqual(["phone-identity:phone:+1"])
  })
  it("takes a phone and whoever appears on it", () => {
    expect(graphScopeKeys({ ...EMPTY_SCOPE, phones: [P1] }, NODES, EDGES)).toEqual(["phone-extraction:p1", "phone-identity:phone:+1"])
  })
  it("takes the whole phone layer with nothing chosen, never a document", () => {
    expect(graphScopeKeys(EMPTY_SCOPE, NODES, EDGES)).not.toContain("doc-1")
    expect(graphScopeKeys(EMPTY_SCOPE, NODES, EDGES)).toHaveLength(4)
  })
})

describe("what the Graph cannot show", () => {
  it("says how many are left out and why", () => {
    const [words] = graphScopeLimits({ ...EMPTY_SCOPE, phones: [P1] }, 120, 2194)
    expect(words).toMatch(/^Showing 120 of 2,194 people and phones in this scope\. The other 2,074 are not drawn/)
  })
  it("says when all of it is shown", () => {
    expect(graphScopeLimits(EMPTY_SCOPE, 4, 4)).toEqual(["Showing all 4 people and phones in this scope."])
  })
  it("never claims a whole while the count is pending", () => {
    expect(graphScopeLimits(EMPTY_SCOPE, 4, null)).toEqual(["Showing 4 people and phones."])
  })
  it("states direction, kinds, labels and dates, each of which it cannot apply in full", () => {
    const scope: Scope = { ...EMPTY_SCOPE, people: [{ key: "a", label: "A" }], mode: "sent-by", kinds: ["call"], labels: [{ id: "l", label: "Follow up" }], window: { from: "2023-01-01", to: "2023-01-02" } }
    const words = graphScopeLimits(scope, 1, 1).join(" ")
    for (const part of [/direction chosen is not applied/, /kind of record/, /by label/, /counts on communication edges/]) expect(words).toMatch(part)
  })
})
