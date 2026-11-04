import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it } from "vitest"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphNode } from "@/types/graph.types"
import { GraphLegend } from "./GraphLegend"

const node = (key: string, type: string) => ({ key, id: key, label: key, type }) as unknown as GraphNode
const all = [node("p1", "Person"), node("p2", "Person"), node("p3", "Person"), node("c1", "Company")]

beforeEach(() => useGraphStore.setState({ subgraphNodeKeys: new Set(), selectedNodeKeys: new Set() }))

it("a type's spotlight takes every node of that type in the case, including those a filter hides (BUG-015)", () => {
  render(<GraphLegend nodes={[all[0], all[3]]} allNodes={all} />)
  expect(screen.getByTestId("legend-count-Person").textContent).toBe("1 of 3")
  fireEvent.click(screen.getByRole("button", { name: "Put all 3 Person in the spotlight" }))
  expect(Array.from(useGraphStore.getState().subgraphNodeKeys).sort()).toEqual(["p1", "p2", "p3"])
})

it("unfiltered, the count is the plain total", () => {
  render(<GraphLegend nodes={all} />)
  expect(screen.getByTestId("legend-count-Person").textContent).toBe("3")
})
