import { act, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { resetRequestsForTest } from "@/lib/request-progress"
import { TooltipProvider } from "@/components/ui/tooltip"

// The map itself (MapLibre) is not under test here: only what the page shows before and instead of it.
vi.mock("./MapCanvas", () => ({ MapCanvas: () => <div data-testid="map-canvas" /> }))

import { MapPage } from "./MapPage"

const CASE = "c0ffee00-0000-4000-8000-000000000001"

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
      <MemoryRouter initialEntries={[`/cases/${CASE}/map`]}>
        <Routes>
          <Route path="/cases/:id/map" element={<MapPage />} />
        </Routes>
      </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }))

beforeEach(() => {
  resetRequestsForTest()
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

it("shows the loading panel in words while the located entities are read, not a bare spinner", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "setInterval", "performance", "requestAnimationFrame", "cancelAnimationFrame"] })
  // Every read stays open, as a slow answer does.
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)))
  mount()
  await act(async () => {
    vi.advanceTimersByTime(800)
  })
  const panel = screen.getByRole("status")
  expect(panel.textContent).toMatch(/located entities/)
  expect(panel.textContent).toMatch(/0 of \d+ parts? loaded/)
  expect(screen.getByRole("progressbar")).toBeTruthy()
})

it("names a failed read with a retry instead of saying the case has no location data", async () => {
  let locationsAsked = 0
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.startsWith("/api/graph/locations/needs-review")) return json([])
      if (url.startsWith("/api/graph/locations")) {
        locationsAsked += 1
        return json({ detail: "Neo4j unavailable" }, 500)
      }
      if (url.startsWith("/api/phones/map/summary")) return json({ case_id: CASE, positioned: 0, total: 0, by_source: {}, bbox: null, not_positionable: [] })
      return json({})
    }),
  )
  mount()
  const alert = await screen.findByTestId("map-load-failed")
  expect(alert.textContent).toMatch(/could not load the case's located entities/)
  expect(screen.queryByText("No location data")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Try again" }))
  await vi.waitFor(() => expect(locationsAsked).toBe(2))
})

it("says which part is missing when the map shows only what did load", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.startsWith("/api/graph/locations/needs-review")) return json([])
      if (url.startsWith("/api/graph/locations")) return json({ detail: "Neo4j unavailable" }, 500)
      if (url.startsWith("/api/phones/map/summary")) return json({ case_id: CASE, positioned: 3, total: 3, by_source: { device_location: 3 }, bbox: [-74, 40, -73, 41], not_positionable: [] })
      return json({})
    }),
  )
  mount()
  const alert = await screen.findByTestId("map-part-failed")
  expect(alert.textContent).toMatch(/could not load the case's located entities; what is shown does not include them/)
  expect(screen.getByTestId("map-canvas")).toBeTruthy()
})
