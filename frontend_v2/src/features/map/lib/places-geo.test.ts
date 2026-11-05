import { describe, expect, it } from "vitest"
import { PLACE_LABEL, placeName, positionFeatures, togetherLines, trajectory } from "./places-geo"

const p = (id: number, phone: string, t: string, radius: number | null = 20) => ({
  id, extraction_id: phone, lat: 40 + id / 1000, lon: -74, radius_m: radius, start_utc: t, end_utc: t, kind: "presence", source_kind: "gps",
})

describe("places on the map (04 8.3)", () => {
  it("draws moves in time order per phone and leaves a move over 2 hours as a gap", () => {
    const t = trajectory([
      p(3, "a", "2023-03-14T12:00:00Z"), p(1, "a", "2023-03-14T09:00:00Z"), p(2, "a", "2023-03-14T09:30:00Z"),
      p(4, "a", "2023-03-14T13:59:00Z"), p(5, "b", "2023-03-14T09:10:00Z"),
    ])
    // a: 09:00 -> 09:30 drawn, 09:30 -> 12:00 is 2 h 30 min (a gap), 12:00 -> 13:59 drawn; b has one point (no line)
    expect(t.gaps).toBe(1)
    expect(t.segments).toBe(2)
    expect(t.lines.features).toHaveLength(2)
    expect(t.lines.features[0].geometry.coordinates).toEqual([[-74, 40.001], [-74, 40.002]])
  })

  it("draws a radius only where one is stated and keeps every position as a dot", () => {
    const f = positionFeatures([p(1, "a", "2023-03-14T09:00:00Z"), p(2, "a", "2023-03-14T09:30:00Z", null)])
    expect(f.dots.features).toHaveLength(2)
    expect(f.dots.features[1].properties?.accuracy).toBe("not recorded")
    expect(f.areas.features).toHaveLength(1)
  })

  it("counts Together pairs it cannot draw instead of dropping them, and names places", () => {
    const r = togetherLines([
      { verdict: "compatible", a_lat: 1, a_lon: 2, b_lat: 1, b_lon: 2.001 },
      { verdict: "separated", a_lat: null, a_lon: null, b_lat: 1, b_lon: 2 },
    ])
    expect(r.lines.features).toHaveLength(1)
    expect(r.undrawn).toBe(1)
    expect(r.noPosition).toBe(0)
    const sightings = togetherLines([
      { verdict: "compatible", basis: "shared_cell", a_lat: null, a_lon: null, b_lat: null, b_lon: null },
      { verdict: "compatible", basis: "bluetooth", a_lat: null, a_lon: null, b_lat: null, b_lon: null },
      { verdict: "separated", basis: "coordinates", a_lat: null, a_lon: null, b_lat: 1, b_lon: 2 },
    ])
    expect(sightings.noPosition).toBe(2)
    expect(sightings.undrawn).toBe(1)
    expect(placeName({ cluster_id: 0, label: null })).toBe("Place 1")
    expect(placeName({ cluster_id: 0, label: "Home" })).toBe("Home")
    expect(PLACE_LABEL).toBe("Investigative location, not cell-site opinion")
  })
})
