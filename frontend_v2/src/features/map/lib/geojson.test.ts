import { describe, expect, it } from "vitest"
import { formatDisplayCoordinates, isApproximateLocation, type MapLocation } from "../hooks/use-map-data"
import { locationsToGeoJSON } from "./geojson"

const baseLocation = {
  key: "loc-exact",
  name: "Exact address",
  type: "location",
  latitude: 51.501476,
  longitude: -0.140634,
  manual_correction_history: [],
} satisfies MapLocation

describe("map location GeoJSON", () => {
  it("tags city and neighborhood locations as approximate", () => {
    const locations: MapLocation[] = [
      baseLocation,
      {
        ...baseLocation,
        key: "loc-city",
        name: "City result",
        latitude: 51.507351,
        longitude: -0.127758,
        location_granularity: "city",
      },
      {
        ...baseLocation,
        key: "loc-neighborhood",
        name: "Neighborhood result",
        latitude: 51.515419,
        longitude: -0.141099,
        location_granularity: "neighborhood",
      },
    ]

    const features = locationsToGeoJSON(locations).features

    expect(features.find((feature) => feature.properties.key === "loc-exact")?.properties.isApproximate).toBe(false)
    expect(features.find((feature) => feature.properties.key === "loc-city")?.properties.isApproximate).toBe(true)
    expect(features.find((feature) => feature.properties.key === "loc-neighborhood")?.properties.isApproximate).toBe(true)
  })

  it("rounds displayed coordinates by actual precision", () => {
    expect(
      formatDisplayCoordinates({
        ...baseLocation,
        location_granularity: "city",
      })
    ).toBe("51.50, -0.14")

    expect(
      formatDisplayCoordinates({
        ...baseLocation,
        accuracy_meters: 1500,
      })
    ).toBe("51.50, -0.14")

    expect(isApproximateLocation({ location_granularity: "address" })).toBe(false)
  })

  it("preserves corrected-location provenance on feature properties", () => {
    const [feature] = locationsToGeoJSON([
      {
        ...baseLocation,
        geocoding_provider: "nominatim",
        geocoding_query: "London",
        geocoding_formatted_address: "London, Greater London, England, United Kingdom",
        geocoding_confidence: "medium",
        location_granularity: "city",
        manual_correction_history: [
          {
            moved_by: "investigator",
            moved_at: "2026-07-18T12:00:00+00:00",
            from_latitude: 51.5,
            from_longitude: -0.12,
            to_latitude: 51.501476,
            to_longitude: -0.140634,
          },
        ],
      },
    ]).features

    expect(feature.properties.geocodingProvider).toBe("nominatim")
    expect(feature.properties.geocodingQuery).toBe("London")
    expect(feature.properties.geocodingFormattedAddress).toContain("Greater London")
    expect(feature.properties.displayCoordinatePrecision).toBe(2)
  })
})
