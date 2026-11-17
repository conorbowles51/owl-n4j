/**
 * Lasso and box hit-testing (lx-corroselect C). Pure functions, so the Map and the Graph test the same maths.
 * A hit is decided on the point's own position, never on what is drawn: a clustered Map point inside the lasso is a
 * hit even when the cluster shows one marker.
 */
export interface Pt {
  x: number
  y: number
}

/** Even-odd ray cast. A polygon of fewer than three points holds nothing. */
export function pointInPolygon(p: Pt, poly: Pt[]): boolean {
  if (poly.length < 3) return false
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i]
    const b = poly[j]
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside
  }
  return inside
}

export function pointInBox(p: Pt, a: Pt, b: Pt): boolean {
  return p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x) && p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y)
}

/** Every item whose position is inside the lasso; items with no position are returned apart, so they are said, not lost. */
export function hitTest<T>(items: T[], at: (item: T) => Pt | null, poly: Pt[]): { hits: T[]; unplaced: T[] } {
  const hits: T[] = []
  const unplaced: T[] = []
  for (const item of items) {
    const p = at(item)
    if (!p) unplaced.push(item)
    else if (pointInPolygon(p, poly)) hits.push(item)
  }
  return { hits, unplaced }
}

/** Links whose two ends are both inside the lasso (the graph's "links between them"). */
export function linksBetween<L>(links: L[], ends: (l: L) => [string, string], inside: Set<string>): L[] {
  return links.filter((l) => {
    const [a, b] = ends(l)
    return inside.has(a) && inside.has(b)
  })
}
