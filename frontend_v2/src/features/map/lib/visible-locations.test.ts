import { describe, expect, it } from "vitest"
import type { MapLocation } from "../hooks/use-map-data"
import type { BoundingShape } from "../stores/map.store"
import { getVisibleLocations } from "./visible-locations"

function location(overrides: Partial<MapLocation>): MapLocation {
  return {
    key: overrides.key ?? "loc",
    name: overrides.name ?? "Location",
    type: overrides.type ?? "location",
    latitude: overrides.latitude ?? 0,
    longitude: overrides.longitude ?? 0,
    manual_correction_history: overrides.manual_correction_history ?? [],
    ...overrides,
  }
}

describe("getVisibleLocations", () => {
  const boundingShapes: BoundingShape[] = [
    {
      id: "a",
      coordinates: [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
        [0, 0],
      ],
    },
  ]

  it("combines existing filters with bounding shapes", () => {
    const visible = getVisibleLocations(
      [
        location({ key: "inside", longitude: 5, latitude: 5 }),
        location({ key: "outside", longitude: 20, latitude: 20 }),
        location({ key: "hidden-type", type: "person", longitude: 5, latitude: 5 }),
      ],
      {
        hiddenTypes: new Set(["person"]),
        confidenceThreshold: null,
        confidenceDirection: "above",
        specificityThreshold: null,
        specificityDirection: "at_least",
        needsReviewMode: false,
        boundingShapes,
      }
    )

    expect(visible.map((loc) => loc.key)).toEqual(["inside"])
  })

  it("combines threshold filters with bounding shapes", () => {
    const visible = getVisibleLocations(
      [
        location({
          key: "specific-inside",
          longitude: 5,
          latitude: 5,
          location_specificity: "street",
        }),
        location({
          key: "vague-inside",
          longitude: 5,
          latitude: 5,
          location_specificity: "country",
        }),
      ],
      {
        hiddenTypes: new Set(),
        confidenceThreshold: null,
        confidenceDirection: "above",
        specificityThreshold: "city",
        specificityDirection: "at_least",
        needsReviewMode: false,
        boundingShapes,
      }
    )

    expect(visible.map((loc) => loc.key)).toEqual(["specific-inside"])
  })
})
