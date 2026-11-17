import { describe, expect, it } from "vitest"
import { render } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ConnectionsList } from "@/features/graph/components/ConnectionsList"
import { corroAttrs, memberFromElement, membersFromElement } from "./item-target"

describe("Corroborate on more rows", () => {
  it("a marked passage names the document and keeps its words", () => {
    const { container } = render(<p {...corroAttrs("evidence", "f1", "A kept passage", { quote: "I was home all evening" })}><span id="in">x</span></p>)
    expect(memberFromElement(container.querySelector("#in"))).toEqual({ type: "evidence", id: "f1", label: "A kept passage", quote: "I was home all evening" })
  })
  it("a graph link stands for both of its ends", () => {
    const { container } = render(<div {...corroAttrs("graph_entity", "b", "paid: B", { also: [{ type: "graph_entity", id: "a" }] })}><i id="in" /></div>)
    expect(membersFromElement(container.querySelector("#in")).map((m) => m.id)).toEqual(["b", "a"])
  })
  it("the graph connections list marks each link with its two entities", () => {
    const { container } = render(<QueryClientProvider client={new QueryClient()}><ConnectionsList caseId="c1" entity={{ key: "a", label: "A" }}
      connections={[{ relationshipType: "PAID", nodes: [{ key: "b", label: "B", type: "Person", direction: "outgoing" }] } as never]} /></QueryClientProvider>)
    const host = container.querySelector("[data-corro]")
    expect(host?.getAttribute("data-corro")).toBe("graph_entity:b")
    expect(host?.getAttribute("data-corro-also")).toBe("graph_entity:a")
  })
})
