export type LngLatPoint = [number, number]

interface ShapeLike {
  coordinates: LngLatPoint[]
}

const EPSILON = 1e-9

function samePoint(a: LngLatPoint, b: LngLatPoint) {
  return Math.abs(a[0] - b[0]) < EPSILON && Math.abs(a[1] - b[1]) < EPSILON
}

function isPointOnSegment(point: LngLatPoint, a: LngLatPoint, b: LngLatPoint) {
  const [x, y] = point
  const [x1, y1] = a
  const [x2, y2] = b
  const cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)

  if (Math.abs(cross) > EPSILON) return false

  return (
    x >= Math.min(x1, x2) - EPSILON &&
    x <= Math.max(x1, x2) + EPSILON &&
    y >= Math.min(y1, y2) - EPSILON &&
    y <= Math.max(y1, y2) + EPSILON
  )
}

function getOpenRing(ring: LngLatPoint[]) {
  if (ring.length > 1 && samePoint(ring[0], ring[ring.length - 1])) {
    return ring.slice(0, -1)
  }
  return ring
}

export function closeRing(points: LngLatPoint[]) {
  const first = points[0]
  const last = points[points.length - 1]
  if (!first || !last) return points
  if (samePoint(first, last)) return points
  return [...points, first]
}

export function boundsToClosedRing(start: LngLatPoint, end: LngLatPoint) {
  return closeRing([
    [start[0], start[1]],
    [end[0], start[1]],
    [end[0], end[1]],
    [start[0], end[1]],
  ])
}

export function pointInPolygon(point: LngLatPoint, ring: LngLatPoint[]) {
  const polygon = getOpenRing(ring)
  if (polygon.length < 3) return false

  const [x, y] = point
  let inside = false

  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]

    if (isPointOnSegment(point, polygon[j], polygon[i])) return true

    const intersects =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi

    if (intersects) inside = !inside
  }

  return inside
}

export function pointInAnyShape(point: LngLatPoint, shapes: ShapeLike[]) {
  if (shapes.length === 0) return true
  return shapes.some((shape) => pointInPolygon(point, shape.coordinates))
}
