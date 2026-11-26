import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
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
    <MemoryRouter><QueryClientProvider client={queryClient}>
      <MapToolbar caseId="case-1" locations={[]} />
    </QueryClientProvider></MemoryRouter>
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

describe("MapToolbar rescan control (DKT-692)", () => {
  beforeEach(() => {
    useMapStore.getState().reset()
  })

  it("does not render the deprecated rescan control", () => {
    renderToolbar()

    expect(
      screen.queryByRole("button", { name: /rescan/i })
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/rescan/i)).not.toBeInTheDocument()
  })
})

describe("MapToolbar count with the phone layer", () => {
  it("counts the phone positions the layer draws beside the case's locations, never a bare 0 locations", () => {
    const queryClient = new QueryClient()
    const { rerender } = render(
      <MemoryRouter><QueryClientProvider client={queryClient}>
        <MapToolbar caseId="case-1" locations={[]} phonePositions={1234} />
      </QueryClientProvider></MemoryRouter>
    )
    expect(screen.getByText("0 locations · 1,234 phone positions")).toBeInTheDocument()
    rerender(
      <MemoryRouter><QueryClientProvider client={queryClient}>
        <MapToolbar caseId="case-1" locations={[]} phonePositions={null} />
      </QueryClientProvider></MemoryRouter>
    )
    expect(screen.getByText("0 locations")).toBeInTheDocument()
  })
})

describe("MapToolbar area banner with the phone layer (sitefilms 15 Nov)", () => {
  beforeEach(() => {
    useMapStore.setState({ boundingShapes: [{ id: "a1", coordinates: [[0, 0], [1, 0], [1, 1], [0, 1]] }] } as never)
  })
  it("counts the phone positions inside the area beside the case's locations, never a bare 0 of 0", () => {
    const queryClient = new QueryClient()
    const ui = (v: number | "counting" | null) => (
      <MemoryRouter><QueryClientProvider client={queryClient}>
        <MapToolbar caseId="case-1" locations={[]} phonePositions={4000} areaPhonePositions={v} />
      </QueryClientProvider></MemoryRouter>
    )
    const { rerender } = render(ui("counting"))
    expect(screen.getByText(/Showing 0 of 0 case locations; counting phone positions inside the area \(1 area\)/)).toBeInTheDocument()
    rerender(ui(106))
    expect(screen.getByText(/Showing 0 of 0 case locations; 106 phone positions inside the area \(1 area\)/)).toBeInTheDocument()
  })
  it("keeps the old wording when the phone layer is off", () => {
    const queryClient = new QueryClient()
    render(
      <MemoryRouter><QueryClientProvider client={queryClient}>
        <MapToolbar caseId="case-1" locations={[]} />
      </QueryClientProvider></MemoryRouter>
    )
    expect(screen.getByText(/Showing 0 of 0 locations \(1 area\)/)).toBeInTheDocument()
  })
})
