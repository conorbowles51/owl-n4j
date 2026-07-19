import { describe, expect, it } from "vitest"
import { pointInAnyShape, pointInPolygon, type LngLatPoint } from "./geometry"

describe("geometry", () => {
  const square: LngLatPoint[] = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
    [0, 0],
  ]

  describe("pointInPolygon", () => {
    it("keeps a point clearly inside a polygon", () => {
      expect(pointInPolygon([5, 5], square)).toBe(true)
    })

    it("filters a point clearly outside a polygon", () => {
      expect(pointInPolygon([12, 5], square)).toBe(false)
    })

    it("keeps a point on a polygon vertex", () => {
      expect(pointInPolygon([0, 0], square)).toBe(true)
    })
  })

  describe("pointInAnyShape", () => {
    const shapeA = { coordinates: square }
    const shapeB = {
      coordinates: [
        [20, 20],
        [30, 20],
        [30, 30],
        [20, 30],
        [20, 20],
      ] satisfies LngLatPoint[],
    }

    it("uses union semantics across disjoint shapes", () => {
      expect(pointInAnyShape([5, 5], [shapeA, shapeB])).toBe(true)
      expect(pointInAnyShape([25, 25], [shapeA, shapeB])).toBe(true)
      expect(pointInAnyShape([15, 15], [shapeA, shapeB])).toBe(false)
    })

    it("passes every point when no shape filter is active", () => {
      expect(pointInAnyShape([500, 500], [])).toBe(true)
    })
  })
})
