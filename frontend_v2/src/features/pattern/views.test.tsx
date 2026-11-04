import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import { patternAPI, type PlacesResponse, type RoutineResponse, type SubjectList } from "./api"
import { PlacesView } from "./components/PatternsPage"
import { TogetherView } from "./components/PlacesViews"

// MapLibre needs WebGL; the map's layers are checked in places-geo.test.ts. Here the map is a stand-in that shows
// what it was given.
vi.mock("@/features/map/components/PlacesMap", () => ({
  PlacesMap: ({ layers }: { layers: Record<string, { features: unknown[] } | undefined> }) => (
    <div data-testid="places-map">{Object.entries(layers).map(([k, v]) => `${k}:${v?.features.length ?? 0}`).join(" ")}</div>
  ),
}))

// The body GET /api/pattern/{case}/places returns (routers/pattern_of_life.py get_places): the rows are under
// "observations". The screen once read "items" and crashed the page on live.
const body: PlacesResponse = {
  total: 3, returned: 2, next_cursor: 2, page_size: 2,
  observations: [
    { id: 1, extraction_id: "e1", record_uid: null, kind: "presence", source_kind: "gps", lat: 40, lon: -74, radius_m: 12.4, radius_basis: "reported",
      start_utc: "2023-03-14T10:00:00+00:00", end_utc: "2023-03-14T10:00:00+00:00", source_app: null },
    { id: 2, extraction_id: "e1", record_uid: null, kind: "presence", source_kind: "wifi", lat: 40.001, lon: -74, radius_m: null, radius_basis: "none",
      start_utc: "2023-03-14T11:00:00+00:00", end_utc: "2023-03-14T11:00:00+00:00", source_app: null },
  ],
  towers_not_placed: [], reverse_geocoding: { enabled: false, reason: "No reverse geocoder is configured." },
}
const routine: RoutineResponse = {
  parameters: {}, zone: "UTC", routine_places: [0], presence_days: 30, observations_used: 900, stays_total: 61, label: "Investigative location, not cell-site opinion",
  places: [
    { cluster_id: 0, lat: 40, lon: -74, radius_m: 60, stay_count: 40, day_count: 28, routine: true, label: null, place_id: null, label_by: null,
      first_utc: "2023-02-01T00:00:00Z", last_utc: "2023-03-14T00:00:00Z" },
    { cluster_id: 1, lat: 40.03, lon: -74, radius_m: 80, stay_count: 3, day_count: 2, routine: false, label: "Gym", place_id: "p1", label_by: "Neil",
      first_utc: "2023-02-01T00:00:00Z", last_utc: "2023-03-14T00:00:00Z" },
  ],
}

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>)
}

describe("Places over time", () => {
  it("draws the positions, routine places and trajectory on the map and states the totals", async () => {
    vi.spyOn(patternAPI, "places").mockResolvedValue(body)
    vi.spyOn(patternAPI, "routine").mockResolvedValue(routine)
    vi.spyOn(patternAPI, "deviations").mockResolvedValue({ threshold: 2, days_scored: 30, label: "x",
      flagged: [{ date: "2023-03-07", score_bits: 4, expectation: "Usually at Place 1 on Tuesdays 21:00 to 00:00.", hours: [{ hour: 21, place: "elsewhere" }, { hour: 22, place: "elsewhere" }] }] })
    wrap(<PlacesView caseId="c" subject={{ kind: "extraction", extraction_id: "e1" }} last="2023-03-14" />)
    expect(await screen.findByText(/Showing 2 of 3 positioned records, 2023-03-08 to 2023-03-14/)).toBeTruthy()
    expect(screen.getByText("12 m")).toBeTruthy()
    expect(screen.getByText("Accuracy not recorded")).toBeTruthy()
    expect(screen.getByText(/the rest are on later pages/)).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId("places-map").textContent).toBe("dots:2 areas:1 lines:1 places:1"))
    expect(screen.getByText(/1 moves drawn, 0 gaps of over 2 hours left undrawn/)).toBeTruthy()
    expect(await screen.findByText(/Routine places \(1 of 2 places\)/)).toBeTruthy()
    expect(screen.getByText("Place 1")).toBeTruthy()
    expect(screen.getByText("Gym")).toBeTruthy()
    expect(await screen.findByText(/Usually at Place 1 on Tuesdays 21:00 to 00:00\. On this day 2 hours were somewhere else\./)).toBeTruthy()
    expect(screen.getByText("Investigative location, not cell-site opinion.")).toBeTruthy()
  })

  it("asks the server for the chosen window", async () => {
    const places = vi.spyOn(patternAPI, "places").mockResolvedValue(body)
    vi.spyOn(patternAPI, "routine").mockResolvedValue(routine)
    vi.spyOn(patternAPI, "deviations").mockResolvedValue({ threshold: null, days_scored: 0, flagged: [], label: "x" })
    wrap(<PlacesView caseId="c" subject={{ kind: "extraction", extraction_id: "e1" }} last="2023-03-14" />)
    await screen.findByText(/Showing 2 of 3/)
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2023-01-01" } })
    await waitFor(() => expect(places).toHaveBeenLastCalledWith("c", { kind: "extraction", extraction_id: "e1" }, "2023-01-01T00:00:00Z", "2023-03-15T00:00:00Z", 0))
  })

  it("names a place through the decision route with the person's reason", async () => {
    vi.spyOn(patternAPI, "places").mockResolvedValue(body)
    vi.spyOn(patternAPI, "routine").mockResolvedValue(routine)
    vi.spyOn(patternAPI, "deviations").mockResolvedValue({ threshold: null, days_scored: 0, flagged: [], label: "x" })
    const name = vi.spyOn(patternAPI, "namePlace").mockResolvedValue({ place_id: "p2", decision_id: "d", label: "Home", previous_label: null })
    wrap(<PlacesView caseId="c" subject={{ kind: "extraction", extraction_id: "e1" }} last="2023-03-14" />)
    fireEvent.click(await screen.findByRole("button", { name: "Name this place" }))
    fireEvent.change(screen.getByLabelText("Place name"), { target: { value: "Home" } })
    fireEvent.change(screen.getByLabelText("Why this name"), { target: { value: "Every night" } })
    fireEvent.click(screen.getByRole("button", { name: "Save the name" }))
    await waitFor(() => expect(name).toHaveBeenCalledWith("c", { kind: "extraction", extraction_id: "e1" }, 0, "Home", "Every night", undefined, { lat: expect.any(Number), lon: expect.any(Number) }))
  })
})

describe("Together", () => {
  const list: SubjectList = {
    extractions: [
      { kind: "extraction", extraction_id: "e1", label: "C1", device_zone: null, first: null, last: "2023-03-14T00:00:00Z", projection_status: "ready", event_count: 1, usual_span: null },
      { kind: "extraction", extraction_id: "e2", label: "C2", device_zone: null, first: null, last: "2023-03-10T00:00:00Z", projection_status: "ready", event_count: 1, usual_span: null },
    ],
    dossiers: [{ kind: "dossier", dossier_id: "d1", name: "Person A", extraction_ids: ["e2"] }],
    total_extractions: 2, total_dossiers: 1,
  } as unknown as SubjectList
  it("compares with a phone or a person over the chosen window and draws every pair it holds", async () => {
    const together = vi.spyOn(patternAPI, "together").mockResolvedValue({ id: "r1", status: "done", total: 2, returned: 2, next_cursor: null,
      counts: { compatible: 1, separated: 1 }, episodes: [],
      items: [{ ordinal: 0, verdict: "compatible", basis: "coordinates", at_utc: "x", distance_m: 5, a_lat: 1, a_lon: 1, b_lat: 1, b_lon: 1 },
        { ordinal: 1, verdict: "separated", basis: "coordinates", at_utc: "x", distance_m: 5000, a_lat: 1, a_lon: 1, b_lat: 2, b_lon: 2 }] })
    wrap(<TogetherView caseId="c" subject={{ kind: "extraction", extraction_id: "e1" }} list={list} />)
    expect(screen.getByRole("option", { name: "Person A (person)" })).toBeTruthy()
    expect((await screen.findByTestId("places-map")).textContent).toBe("pairs:2")
    expect(screen.getByText(/The map draws 2 of 2 pairs/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Compare with"), { target: { value: "d:d1" } })
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2023-01-01" } })
    const button = screen.getByRole("button", { name: /Compare 2023-01-01 to/ })
    await waitFor(() => expect(button).not.toBeDisabled())  // the comparison started by choosing the person has ended
    fireEvent.click(button)
    await waitFor(() => expect(together).toHaveBeenLastCalledWith("c", { kind: "extraction", extraction_id: "e1" }, { kind: "dossier", dossier_id: "d1" },
      "2023-01-01T00:00:00Z", expect.any(String)))
  })
})
