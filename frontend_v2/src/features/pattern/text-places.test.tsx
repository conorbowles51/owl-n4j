import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { textPlacesAPI, type TextPlace, type TextPlaceList } from "./text-places-api"
import { TextPlaces } from "./components/TextPlaces"
import { circlePolygon, startRadiusFor, suggestionWords, validPlacement } from "./text-places-lib"

// The map itself is not drawn in jsdom; a click on this stand-in is a click on the map.
vi.mock("./components/TextPlacePicker", () => ({
  default: ({ onPick }: { onPick: (p: { lat: number; lon: number }) => void }) => (
    <button type="button" onClick={() => onPick({ lat: 38.9, lon: -77.03 })}>map click</button>
  ),
}))

const item = (over: Partial<TextPlace> = {}): TextPlace => ({
  extraction_id: "e1", record_uid: "r1", field_path: "Location", model_type: "CalendarEntry", group: "calendar",
  group_words: "Calendar location", kind: "planned", kind_words: "Planned (calendar)",
  place_text: "Synthetic Hall, Springfield, IL", phone_text: "Synthetic Hall, Springfield, IL", corrected: false,
  start_utc: "2023-03-14T09:00:00+00:00", end_utc: "2023-03-14T11:00:00+00:00", placement: null, decisions: 0, ...over,
})

const list = (items: TextPlace[], enabled = true): TextPlaceList => ({
  total: items.length, returned: items.length, cursor: 0, limit: 200, next_cursor: null, items,
  counts: { all: items.length, placed: items.filter((i) => i.placement).length,
    not_placed: items.filter((i) => !i.placement).length, by_group: { calendar: items.length, checkin: 0, other: 0 } },
  status: "all",
  suggestions: enabled ? { enabled: true, places: 5, reason: "Suggested from the GeoNames place list on this server." }
    : { enabled: false, places: 0, reason: "Suggestions are off: the configured nominatim geocoder is not on this server's own network." },
})

function show() {
  return render(<QueryClientProvider client={new QueryClient()}><TextPlaces caseId="c" extractionIds={["e1"]} /></QueryClientProvider>)
}

afterEach(() => vi.restoreAllMocks())

describe("Text places", () => {
  it("lists each written place with its kind and says it is not placed until a person places it", async () => {
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([item()]))
    show()
    expect(await screen.findByText(/1 text place: 0 placed by a person, 1 not placed/)).toBeTruthy()
    expect(screen.getByText("“Synthetic Hall, Springfield, IL”")).toBeTruthy()
    expect(screen.getByText(/Planned \(calendar\)/)).toBeTruthy()
    expect(screen.getByText(/Nothing on the map comes from this text until a person places it/)).toBeTruthy()
  })

  it("a suggestion only fills the point: nothing is saved until the person gives a reason and saves", async () => {
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([item()]))
    vi.spyOn(textPlacesAPI, "suggestions").mockResolvedValue({
      enabled: true, reason: "", total: 7, returned: 1, label: "Suggested, not confirmed", attribution: "Place names: GeoNames",
      candidates: [{ geonameid: 1, name: "Springfield", lat: 39.8, lon: -89.6, country_code: "US", country: "United States",
        admin1: "Illinois", population: 114394 }],
    })
    const place = vi.spyOn(textPlacesAPI, "place").mockResolvedValue({ placement_id: "p", decision_id: "d" })
    show()
    fireEvent.click(await screen.findByText("Place on map"))
    expect(await screen.findByText(/Suggested, not confirmed: 1 of 7 places/)).toBeTruthy()
    fireEvent.click(screen.getByText(/Springfield, Illinois, United States, population 114,394 · suggested/))
    expect((screen.getByLabelText("Latitude") as HTMLInputElement).value).toBe("39.8")
    expect((screen.getByLabelText("Radius (metres)") as HTMLInputElement).value).toBe("8000")
    expect(place).not.toHaveBeenCalled()
    expect((screen.getByText("Save the place") as HTMLButtonElement).disabled).toBe(true) // no reason yet
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "The town in the entry" } })
    fireEvent.click(screen.getByText("Save the place"))
    await waitFor(() => expect(place).toHaveBeenCalledTimes(1))
    expect(place.mock.calls[0][1]).toMatchObject({ record_uid: "r1", field_path: "Location", lat: 39.8, lon: -89.6,
      radius_m: 8000, reason: "The town in the entry" })
    expect(place.mock.calls[0][1].suggestion?.geonameid).toBe(1)
  })

  it("a point the person clicks on the map is saved as theirs, without the suggestion", async () => {
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([item()]))
    vi.spyOn(textPlacesAPI, "suggestions").mockResolvedValue({ enabled: true, reason: "", total: 1, returned: 1,
      candidates: [{ geonameid: 1, name: "Springfield", lat: 39.8, lon: -89.6, country_code: "US", admin1: "Illinois", population: 1 }] })
    const place = vi.spyOn(textPlacesAPI, "place").mockResolvedValue({ placement_id: "p", decision_id: "d" })
    show()
    fireEvent.click(await screen.findByText("Place on map"))
    fireEvent.click(await screen.findByText(/· suggested/))
    fireEvent.click(await screen.findByText("map click"))
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Seen on the map" } })
    fireEvent.click(screen.getByText("Save the place"))
    await waitFor(() => expect(place).toHaveBeenCalledTimes(1))
    expect(place.mock.calls[0][1]).toMatchObject({ lat: 38.9, lon: -77.03, suggestion: null })
  })

  it("suggestions off: the reason is shown and none are asked for", async () => {
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([item()], false))
    const sugg = vi.spyOn(textPlacesAPI, "suggestions")
    show()
    expect(await screen.findByText(/Suggestions are off: the configured nominatim geocoder/)).toBeTruthy()
    fireEvent.click(screen.getByText("Place on map"))
    expect(sugg).not.toHaveBeenCalled()
  })

  it("a placed text shows who placed it, the text as it was then and its decisions, and can be removed", async () => {
    const placed = item({
      place_text: "Synthetic Hall, Springfield", phone_text: "Synthetic Hal, Springfield", corrected: true, decisions: 2,
      placement: { id: "p2", lat: 39.8, lon: -89.6, radius_m: 300, reason: "closer", suggestion: null, decision_id: "d2",
        actor_name: "Test Person", created_at: "2026-11-04T12:00:00+00:00", place_text: "Synthetic Hal, Springfield" },
    })
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([placed]))
    vi.spyOn(textPlacesAPI, "history").mockResolvedValue({ total: 2, items: [
      { id: "p1", place_text: "Synthetic Hal, Springfield", lat: 39.7, lon: -89.5, radius_m: 2000, reason: "first",
        suggestion: null, decision_id: "d1", removed_decision_id: "d2", actor_name: "Test Person", created_at: "2026-11-04T11:00:00+00:00",
        ended_by: "place_text_place" },
      { id: "p2", place_text: "Synthetic Hal, Springfield", lat: 39.8, lon: -89.6, radius_m: 300, reason: "closer",
        suggestion: null, decision_id: "d2", removed_decision_id: null, actor_name: "Test Person", created_at: "2026-11-04T12:00:00+00:00" },
    ] })
    const remove = vi.spyOn(textPlacesAPI, "remove").mockResolvedValue({ decision_id: "d3" })
    show()
    expect(await screen.findByText(/within 300 m by Test Person/)).toBeTruthy()
    expect(screen.getByText(/The phone recorded: “Synthetic Hal, Springfield”/)).toBeTruthy()
    expect(screen.getByText(/The text read “Synthetic Hal, Springfield” when it was placed/)).toBeTruthy()
    fireEvent.click(screen.getByText("Decisions (2)"))
    expect(await screen.findByText(/“first”. Text then: “Synthetic Hal, Springfield”. Replaced by the next placement./)).toBeTruthy()
    fireEvent.click(screen.getByText("Remove the place"))
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "wrong hall" } })
    fireEvent.click(screen.getByText("Remove"))
    await waitFor(() => expect(remove).toHaveBeenCalledWith("c", { record_uid: "r1", field_path: "Location", reason: "wrong hall" }))
  })

  it("a placement that no longer applies is listed with why and can be removed", async () => {
    const data = { ...list([]), counts: { ...list([]).counts, no_longer_applies: 1 }, no_longer_applies: [{
      id: "p9", lat: 39.8, lon: -89.6, radius_m: 300, reason: "the hall", suggestion: null, decision_id: "d9",
      actor_name: "Test Person", created_at: "2026-11-04T12:00:00+00:00", place_text: "Synthetic Hall, Springfield",
      extraction_id: "e1", record_uid: "r9", field_path: "Location", model_type: "CalendarEntry",
      reason_words: "This placement no longer applies: the record now has a position.",
    }] }
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(data)
    const remove = vi.spyOn(textPlacesAPI, "remove").mockResolvedValue({ decision_id: "d10" })
    show()
    expect(await screen.findByText(/1 placement no longer applies and is not on the map/)).toBeTruthy()
    expect(screen.getByText(/This placement no longer applies: the record now has a position/)).toBeTruthy()
    fireEvent.click(screen.getByText("Remove the place"))
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "has a position now" } })
    fireEvent.click(screen.getByText("Remove"))
    await waitFor(() => expect(remove).toHaveBeenCalledWith("c", { record_uid: "r9", field_path: "Location", reason: "has a position now" }))
  })

  it("re-placing at a saved suggestion's point after a reload keeps the suggestion", async () => {
    const sug = { geonameid: 1, name: "Springfield", lat: "39.80172", lon: "-89.64371", country_code: "US",
      admin1: "Illinois", population: 114394 }
    const placed = item({ placement: { id: "p1", lat: 39.801720, lon: -89.643710, radius_m: 8000, reason: "the town",
      suggestion: sug, decision_id: "d1", actor_name: "Test Person", created_at: "2026-11-04T12:00:00+00:00",
      place_text: "Synthetic Hall, Springfield, IL" } })
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([placed], false))
    const place = vi.spyOn(textPlacesAPI, "place").mockResolvedValue({ placement_id: "p2", decision_id: "d2" })
    show()
    fireEvent.click(await screen.findByText("Change the place"))
    fireEvent.change(screen.getByLabelText("Radius (metres)"), { target: { value: "3000" } })
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "narrower" } })
    fireEvent.click(screen.getByText("Save the place"))
    await waitFor(() => expect(place).toHaveBeenCalled())
    expect(place.mock.calls[0][1]).toMatchObject({ radius_m: 3000, suggestion: sug })
  })

  it("a refused save says why in plain words", async () => {
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([item()], false))
    vi.spyOn(textPlacesAPI, "place").mockRejectedValue(Object.assign(new Error("Forbidden"), { status: 403 }))
    show()
    fireEvent.click(await screen.findByText("Place on map"))
    fireEvent.click(await screen.findByText("map click"))
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "x" } })
    fireEvent.click(screen.getByText("Save the place"))
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "You can view this case but not change it.")
  })
})

describe("text place helpers", () => {
  it("draws the radius as a closed ring at the right distance", () => {
    const ring = circlePolygon(0, 0, 1000).geometry.coordinates[0]
    expect(ring[0]).toEqual(ring[ring.length - 1])
    expect(Math.abs(ring[0][1] - 0.008993)).toBeLessThan(0.00001) // 1 km north of the equator
  })
  it("checks the point and radius the server accepts", () => {
    expect(validPlacement("1", "2", "100")).toBe(true)
    expect(validPlacement("91", "2", "100")).toBe(false)
    expect(validPlacement("1", "2", "0")).toBe(false)
    expect(validPlacement("1", "2", "1.5")).toBe(false)
    expect(validPlacement("", "2", "100")).toBe(false)
  })
  it("words a suggestion and starts a town's radius wide", () => {
    expect(suggestionWords({ name: "Paris", admin1: null, country: "France", country_code: "FR", population: null })).toBe("Paris, France")
    expect(startRadiusFor(2_000_000)).toBe(20000)
    expect(startRadiusFor(null)).toBe(2000)
  })
})

describe("text place history", () => {
  it("shows a removal with who removed it and why", async () => {
    const it2 = item({ decisions: 2 })
    vi.spyOn(textPlacesAPI, "list").mockResolvedValue(list([it2]))
    vi.spyOn(textPlacesAPI, "history").mockResolvedValue({ total: 1, items: [
      { id: "p1", place_text: "Synthetic Hall, Springfield, IL", lat: 39.7, lon: -89.5, radius_m: 2000, reason: "first",
        suggestion: null, decision_id: "d1", removed_decision_id: "d2", actor_name: "Test Person", created_at: "2026-11-04T11:00:00+00:00",
        ended_by: "remove_text_place", ended_reason: "wrong hall", ended_actor_name: "Other Person", ended_at: "2026-11-04T12:00:00+00:00" },
    ] })
    show()
    fireEvent.click(await screen.findByText("Decisions (2)"))
    expect(await screen.findByText(/Removed on 2026-11-04 12:00 UTC by Other Person: “wrong hall”./)).toBeTruthy()
  })
})
