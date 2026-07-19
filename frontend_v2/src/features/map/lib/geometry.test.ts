import { describe, expect, it } from "vitest"
import {
  boundsToClosedRing,
  closeRing,
  pointInAnyShape,
  pointInPolygon,
  type LngLatPoint,
} from "./geometry"

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

  describe("ring helpers", () => {
    it("closes an open ring without duplicating an already closed ring", () => {
      expect(
        closeRing([
          [0, 0],
          [1, 0],
          [1, 1],
        ])
      ).toEqual([
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 0],
      ])
      expect(closeRing(square)).toEqual(square)
    })

    it("creates a closed rectangular ring from drag bounds", () => {
      expect(boundsToClosedRing([1, 2], [3, 4])).toEqual([
        [1, 2],
        [3, 2],
        [3, 4],
        [1, 4],
        [1, 2],
      ])
    })
  })
})
