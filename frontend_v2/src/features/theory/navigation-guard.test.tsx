import { act, renderHook, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { useGraphStore } from "@/stores/graph.store"
import { useOpenGroup } from "./source-links"

afterEach(() => vi.restoreAllMocks())
function Where() {
  return <span data-testid="guard-route">{useLocation().pathname}</span>
}

it("guards a theory's source navigation before changing the destination selection", () => {
  const guard = vi.fn().mockReturnValue(false)
  const select = vi.spyOn(useGraphStore.getState(), "selectNodes")
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={["/cases/example/workspace"]}>{children}<Where /></MemoryRouter>
  const { result } = renderHook(() => useOpenGroup("example", guard), { wrapper })
  const target = { label: "Addresses under review", linkId: "source-1", targetType: "map_selection", members: [{ type: "graph_entity", id: "entity-1" }] }
  act(() => result.current(target))
  expect(guard).toHaveBeenCalledOnce()
  expect(select).not.toHaveBeenCalled()
  expect(screen.getByTestId("guard-route")).toHaveTextContent("/cases/example/workspace")
  guard.mockReturnValue(true)
  act(() => result.current(target))
  expect(select).toHaveBeenCalledWith(["entity-1"])
  expect(screen.getByTestId("guard-route")).toHaveTextContent("/cases/example/map")
})
