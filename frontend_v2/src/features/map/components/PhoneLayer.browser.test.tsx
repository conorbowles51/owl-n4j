import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it } from "vitest"
import { page } from "vitest/browser"
import { PhoneLayerPanel } from "./PhoneLayer"

afterEach(() => cleanup())

const summary = {
  case_id: "c", by_phone: [], positioned: 1, total: 5, by_source: { device_location: 1 }, bbox: [-74, 40, -73, 41] as [number, number, number, number],
  not_positionable: [{ reason: "Cell tower records without a position: the production gives tower identifiers only", model_type: "CellTower", count: 4, phones: 1 }],
}
const point = {
  type: "point" as const, point_uid: "a", record_uid: "r-a", extraction_id: "e", phone_label: "Phone 2", lat: 40, lon: -74,
  accuracy_m: 7, accuracy_words: "Within 7 m", source_words: "Location services", affiliation: null, instant: "2024-01-02T12:30:00Z",
  time: { full: "Tue, Jan 2, 2024, 12:30:00 PM UTC" }, model_type: "Location", flags: [], deleted_state: null,
}

it("at 390 wide the Phone positions panel stays inside the map (lx-overlapviews-b, 18 Nov)", async () => {
  await page.viewport(390, 844)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        {/* The map left between the side menu and the right rail on a 390-wide phone. */}
        <div style={{ position: "relative", width: 278, height: 600 }} data-testid="map">
          <PhoneLayerPanel caseId="c" summary={summary} points={{ case_id: "c", total: 1, clustered: false, limits: [], items: [point] }} />
        </div>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const panel = await screen.findByRole("region", { name: "Phone positions" })
  expect(panel.getBoundingClientRect().right).toBeLessThanOrEqual(screen.getByTestId("map").getBoundingClientRect().right)
})
