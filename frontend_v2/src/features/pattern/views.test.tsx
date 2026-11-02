import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import { patternAPI, type PlacesResponse } from "./api"
import { PlacesView } from "./components/PatternsPage"

// The body GET /api/pattern/{case}/places returns (routers/pattern_of_life.py get_places): the rows are under
// "observations". The screen once read "items" and crashed the page on live.
const body: PlacesResponse = {
  total: 3, returned: 2, next_cursor: 2, page_size: 2,
  observations: [
    { id: 1, extraction_id: "e1", record_uid: null, kind: "presence", source_kind: "gps", radius_m: 12.4, radius_basis: "reported",
      start_utc: "2023-03-14T10:00:00+00:00", end_utc: "2023-03-14T10:00:00+00:00", source_app: null },
    { id: 2, extraction_id: "e1", record_uid: null, kind: "presence", source_kind: "wifi", radius_m: null, radius_basis: "none",
      start_utc: "2023-03-14T11:00:00+00:00", end_utc: "2023-03-14T11:00:00+00:00", source_app: null },
  ],
  towers_not_placed: [], reverse_geocoding: { enabled: false, reason: "No reverse geocoder is configured." },
}

describe("Places over time", () => {
  it("lists the observations the API returns, states the total and that more pages exist", async () => {
    vi.spyOn(patternAPI, "places").mockResolvedValue(body)
    render(<QueryClientProvider client={new QueryClient()}>
      <PlacesView caseId="c" subject={{ kind: "extraction", extraction_id: "e1" }} last="2023-03-14" />
    </QueryClientProvider>)
    expect(await screen.findByText(/Showing 2 of 3 positioned records/)).toBeTruthy()
    expect(screen.getByText("12 m")).toBeTruthy()
    expect(screen.getByText("Accuracy not recorded")).toBeTruthy()
    expect(screen.getByText(/the rest are on later pages/)).toBeTruthy()
  })
})
