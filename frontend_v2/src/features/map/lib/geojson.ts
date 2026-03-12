import type { MapLocation } from "../hooks/use-map-data"
import type { Feature, FeatureCollection, Point, Polygon } from "geojson"

export interface LocationProperties {
  key: string
  name: string
  entityType: string
  locationRaw?: string
  locationFormatted?: string
  geocodingConfidence?: string
  summary?: string
  date?: string
  connectionCount: number
}

export function locationsToGeoJSON(
  locations: MapLocation[]
): FeatureCollection<Point, LocationProperties> {
  return {
    type: "FeatureCollection",
    features: locations.map(
      (loc): Feature<Point, LocationProperties> => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [loc.longitude, loc.latitude],
        },
        properties: {
          key: loc.key,
          name: loc.name,
          entityType: loc.type,
          locationRaw: loc.location_raw,
          locationFormatted: loc.location_formatted,
          geocodingConfidence: loc.geocoding_confidence,
          summary: loc.summary,
          date: loc.date,
          connectionCount: loc.connections?.length ?? 0,
        },
      })
    ),
  }
}

export function createCircleGeoJSON(
  center: [number, number],
  radiusKm: number,
  steps = 64
): FeatureCollection<Polygon> {
  const [lng, lat] = center
  const coords: [number, number][] = []

  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    const dx = radiusKm / (111.32 * Math.cos((lat * Math.PI) / 180))
    const dy = radiusKm / 110.574
    coords.push([lng + dx * Math.cos(angle), lat + dy * Math.sin(angle)])
  }

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [coords] },
        properties: {},
      },
    ],
  }
}
