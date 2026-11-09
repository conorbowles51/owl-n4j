/**
 * The edge under a right-click (GR-01). Edges have no hit area on the canvas (drawing one for every edge on every
 * frame cost about 6 s of a 25 s layout on a large case), so the edge is found only when someone right-clicks:
 * one pass over the edges, nearest line within the tolerance.
 */
export interface HitLink {
  source: { x?: number; y?: number; key?: string } | string
  target: { x?: number; y?: number; key?: string } | string
  type: string
}

function distanceToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2))
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.hypot(px - cx, py - cy)
}

export function nearestLink<L extends HitLink>(links: readonly L[], x: number, y: number, tolerance: number): L | null {
  let best: L | null = null
  let bestDistance = tolerance
  for (const link of links) {
    const s = link.source
    const t = link.target
    if (typeof s !== "object" || typeof t !== "object") continue
    if (s.x == null || s.y == null || t.x == null || t.y == null) continue
    const d = distanceToSegment(x, y, s.x, s.y, t.x, t.y)
    if (d <= bestDistance) {
      best = link
      bestDistance = d
    }
  }
  return best
}

export function linkEndKey(end: HitLink["source"]): string {
  return typeof end === "object" ? String(end.key ?? "") : String(end)
}
