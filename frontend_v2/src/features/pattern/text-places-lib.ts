import type { Feature, Polygon } from "geojson"

/** A circle of ``radiusM`` metres around a point as a 48-sided polygon (spherical, adequate under 50 km). */
export function circlePolygon(lat: number, lon: number, radiusM: number, sides = 48): Feature<Polygon> {
  const R = 6371008.8
  const d = radiusM / R
  const p1 = (lat * Math.PI) / 180
  const l1 = (lon * Math.PI) / 180
  const ring: [number, number][] = []
  for (let i = 0; i < sides; i++) {
    const b = (2 * Math.PI * i) / sides
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b))
    const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2))
    ring.push([(l2 * 180) / Math.PI, (p2 * 180) / Math.PI])
  }
  ring.push(ring[0])  // a closed ring ends on its first vertex exactly
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }
}

export function validPlacement(lat: string, lon: string, radius: string) {
  const la = Number(lat), lo = Number(lon), r = Number(radius)
  return lat.trim() !== "" && lon.trim() !== "" && Number.isFinite(la) && Number.isFinite(lo) &&
    la >= -90 && la <= 90 && lo >= -180 && lo <= 180 && Number.isInteger(r) && r >= 1 && r <= 50000
}

/** A suggestion's own words: name, region, country and population when the place list has one. */
export function suggestionWords(s: { name: string; admin1: string | null; country?: string | null; country_code: string | null;
  population: number | string | null }) {
  const where = [s.admin1, s.country || s.country_code].filter(Boolean).join(", ")
  const pop = s.population != null && Number(s.population) > 0 ? `, population ${Number(s.population).toLocaleString()}` : ""
  return `${s.name}${where ? `, ${where}` : ""}${pop}`
}

/** Radius for a suggestion the person starts from: a town is an area, so start wide; the person narrows it. */
export function startRadiusFor(population: number | string | null) {
  const p = Number(population || 0)
  if (p >= 1_000_000) return 20000
  if (p >= 100_000) return 8000
  if (p >= 10_000) return 4000
  return 2000
}

/** Whether a point is the one a suggestion offers. The ledger keeps a suggestion's point to 5 decimal places, so a
 * point read back from a saved suggestion still counts as the suggestion's own. */
export function atSuggestion(s: { lat: number | string; lon: number | string } | null | undefined, lat: number, lon: number): boolean {
  if (!s) return false
  return Math.abs(Number(s.lat) - lat) <= 0.0000051 && Math.abs(Number(s.lon) - lon) <= 0.0000051
}
