import type { Feature, FeatureCollection, LineString, Point, Polygon } from "geojson"
import { createCircleGeoJSON } from "./geojson"

export { PLACE_LABEL } from "./place-label"

/** A move between two positions more than 2 hours apart is a gap, never a line (04 section 8.3). */
export const TRAJECTORY_GAP_MS = 2 * 3600_000

export interface PlacePoint {
  id: number | string
  extraction_id: string | null
  lat: number
  lon: number
  radius_m: number | null
  start_utc: string
  end_utc: string
  kind: string
  source_kind: string
}

export interface Trajectory {
  lines: FeatureCollection<LineString>
  /** Moves not drawn because the phone had no position for over 2 hours. */
  gaps: number
  segments: number
}

/** Lines between consecutive positions of each phone, in time order, broken where two positions are more than
 * ``gapMs`` apart (the end of one to the start of the next). */
export function trajectory(points: PlacePoint[], gapMs = TRAJECTORY_GAP_MS): Trajectory {
  const byPhone = new Map<string, PlacePoint[]>()
  for (const p of points) {
    const k = p.extraction_id ?? ""
    if (!byPhone.has(k)) byPhone.set(k, [])
    byPhone.get(k)!.push(p)
  }
  const features: Feature<LineString>[] = []
  let gaps = 0
  let segments = 0
  for (const [phone, list] of byPhone) {
    const sorted = [...list].sort((a, b) => Date.parse(a.start_utc) - Date.parse(b.start_utc))
    let run: [number, number][] = []
    const flush = () => {
      if (run.length >= 2) {
        features.push({ type: "Feature", properties: { phone }, geometry: { type: "LineString", coordinates: run } })
        segments += run.length - 1
      }
      run = []
    }
    for (let i = 0; i < sorted.length; i++) {
      const p = sorted[i]
      if (i > 0 && Date.parse(p.start_utc) - Date.parse(sorted[i - 1].end_utc) > gapMs) {
        gaps += 1
        flush()
      }
      run.push([p.lon, p.lat])
    }
    flush()
  }
  return { lines: { type: "FeatureCollection", features }, gaps, segments }
}

/** Each position as a point, and each position with a stated radius as its area (the radius used in comparisons). */
export function positionFeatures(points: PlacePoint[]): { dots: FeatureCollection<Point>; areas: FeatureCollection<Polygon> } {
  const dots: Feature<Point>[] = points.map((p) => ({
    type: "Feature",
    properties: { id: String(p.id), phone: p.extraction_id ?? "", accuracy: p.radius_m === null ? "not recorded" : "stated" },
    geometry: { type: "Point", coordinates: [p.lon, p.lat] },
  }))
  const areas: Feature<Polygon>[] = points.filter((p) => p.radius_m !== null && p.radius_m > 0).map((p) => ({
    ...createCircleGeoJSON([p.lon, p.lat], (p.radius_m as number) / 1000, 32).features[0],
    properties: { id: String(p.id), phone: p.extraction_id ?? "" },
  }))
  return { dots: { type: "FeatureCollection", features: dots }, areas: { type: "FeatureCollection", features: areas } }
}

export interface RoutinePlace {
  cluster_id: number
  lat: number
  lon: number
  radius_m: number
  routine: boolean
  label: string | null
}

/** A place in words: its name when a person named it, else its number in this computation. */
export function placeName(p: { cluster_id: number; label: string | null }) {
  return p.label || `Place ${p.cluster_id + 1}`
}

export function routineAreas(places: RoutinePlace[]): FeatureCollection<Polygon> {
  return {
    type: "FeatureCollection",
    features: places.map((p) => ({
      ...createCircleGeoJSON([p.lon, p.lat], Math.max(p.radius_m, 25) / 1000, 48).features[0],
      properties: { name: placeName(p), routine: p.routine ? "yes" : "no" },
    })),
  }
}

export interface TogetherItem {
  verdict: string
  a_lat: number | null
  a_lon: number | null
  b_lat: number | null
  b_lon: number | null
}

/** One line per compared pair between the two positions, keyed by verdict; pairs whose positions are no longer held
 * (a phone rebuilt since the run) are counted, not drawn. */
export function togetherLines(items: TogetherItem[]): { lines: FeatureCollection<LineString>; undrawn: number } {
  const features: Feature<LineString>[] = []
  let undrawn = 0
  for (const it of items) {
    if (it.a_lat === null || it.a_lon === null || it.b_lat === null || it.b_lon === null) {
      undrawn += 1
      continue
    }
    features.push({ type: "Feature", properties: { verdict: it.verdict },
      geometry: { type: "LineString", coordinates: [[it.a_lon, it.a_lat], [it.b_lon, it.b_lat]] } })
  }
  return { lines: { type: "FeatureCollection", features }, undrawn }
}

/** [w, s, e, n] around the given positions, or null. */
export function boundsOf(coords: [number, number][]): [number, number, number, number] | null {
  if (!coords.length) return null
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity
  for (const [x, y] of coords) {
    w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y)
  }
  return [w, s, e, n]
}
