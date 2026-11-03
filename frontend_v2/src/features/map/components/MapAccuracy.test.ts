import { describe, expect, it, vi } from "vitest"
vi.mock("maplibre-gl", () => ({ default: {} }))
vi.mock("react-map-gl/maplibre", () => ({ default: () => null, Source: () => null, Layer: () => null, NavigationControl: () => null }))
import { accuracyPixelsAtZoom20, METRES_PER_PIXEL_Z20 } from "./map-accuracy"

describe("phone accuracy circles (03 section 13.3)", () => {
  it("draw the reported accuracy: 512-pixel tiles and the latitude's scale", () => {
    expect(METRES_PER_PIXEL_Z20).toBeCloseTo(0.07464, 4)
    expect(accuracyPixelsAtZoom20(100, 0)).toBeCloseTo(1339.7, 0)
    // at 53.3 degrees north a 100 m radius is about 2,240 pixels at zoom 20
    expect(accuracyPixelsAtZoom20(100, 53.3)).toBeGreaterThan(2230)
    expect(accuracyPixelsAtZoom20(100, 53.3)).toBeLessThan(2250)
  })
})
