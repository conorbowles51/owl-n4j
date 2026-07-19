import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { useMapStore } from "../stores/map.store"
import { MapToolbar } from "./MapToolbar"

vi.mock("../hooks/use-map-data", () => ({
  useMapReviewQueue: () => ({ data: [] }),
}))

beforeAll(() => {
  // Radix popper needs ResizeObserver, which jsdom lacks
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

function renderToolbar() {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MapToolbar caseId="case-1" locations={[]} />
    </QueryClientProvider>
  )
}

async function openAreasPopover() {
  fireEvent.click(screen.getByRole("button", { name: /Areas/ }))
  await screen.findByText("Area filter")
  // Radix registers its outside-dismiss listener on a timeout after open
  await act(() => new Promise((resolve) => setTimeout(resolve, 0)))
}

function addDraftTriangle() {
  const store = useMapStore.getState()
  store.addDrawingPoint([0, 0])
  store.addDrawingPoint([1, 0])
  store.addDrawingPoint([0, 1])
  store.finishDrawingShape()
}

describe("MapToolbar areas popover", () => {
  beforeEach(() => {
    useMapStore.getState().reset()
  })

  it("stays open on outside clicks while drawing, so Finish/Apply stay reachable", async () => {
    renderToolbar()
    await openAreasPopover()
    fireEvent.click(screen.getByRole("button", { name: "Draw area" }))
    expect(useMapStore.getState().drawMode).toBe(true)

    // A map click lands outside the popover content — it must NOT dismiss
    fireEvent.pointerDown(document.body)
    fireEvent.click(document.body)
    expect(screen.getByText("Area filter")).toBeInTheDocument()
  })

  it("closes on outside clicks when not drawing", async () => {
    renderToolbar()
    await openAreasPopover()

    fireEvent.pointerDown(document.body)
    await waitFor(() =>
      expect(screen.queryByText("Area filter")).not.toBeInTheDocument()
    )
  })

  it("lists a finished shape under Pending and applies it as a union filter", async () => {
    renderToolbar()
    await openAreasPopover()
    fireEvent.click(screen.getByRole("button", { name: "Draw area" }))

    act(() => addDraftTriangle())
    expect(screen.getByText("Pending")).toBeInTheDocument()
    act(() => addDraftTriangle())
    expect(screen.getByText("Area 2")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Apply/ }))
    expect(useMapStore.getState().boundingShapes).toHaveLength(2)
    expect(screen.getByText("Applied")).toBeInTheDocument()
  })
})
