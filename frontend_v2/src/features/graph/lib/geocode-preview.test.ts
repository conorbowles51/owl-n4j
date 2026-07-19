import { describe, expect, it } from "vitest"
import { geocodePreviewMatchesCoordinates, type GeocodePreview } from "./geocode-preview"

const preview: GeocodePreview = {
  query: "London",
  latitude: 51.501,
  longitude: -0.141,
  formattedAddress: "London, UK",
}

describe("geocodePreviewMatchesCoordinates", () => {
  it("keeps a preview active while the saved coordinates still match it", () => {
    expect(
      geocodePreviewMatchesCoordinates(preview, {
        latitude: 51.501,
        longitude: -0.141,
      })
    ).toBe(true)
  })

  it("clears stale preview metadata after the marker is moved manually", () => {
    expect(
      geocodePreviewMatchesCoordinates(preview, {
        latitude: 51.502,
        longitude: -0.141,
      })
    ).toBe(false)
  })
})
