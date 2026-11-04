import { useMemo } from "react"
import Map, { Layer, NavigationControl, Source } from "react-map-gl/maplibre"
import "maplibre-gl/dist/maplibre-gl.css"
import type { FeatureCollection, LineString, Point, Polygon } from "geojson"
import { useMapTheme } from "../hooks/use-map-theme"
import { BasemapNote } from "./BasemapNote"
import { boundsOf } from "../lib/places-geo"
import { PLACE_LABEL } from "../lib/place-label"

const EMPTY = { type: "FeatureCollection", features: [] } as FeatureCollection<never>

export interface PlacesMapLayers {
  dots?: FeatureCollection<Point>
  areas?: FeatureCollection<Polygon>
  lines?: FeatureCollection<LineString>
  places?: FeatureCollection<Polygon>
  pairs?: FeatureCollection<LineString>
}

/**
 * The Case Map's base map and theme (use-map-theme, BasemapNote) drawing the Patterns screen's places: positions
 * with their radii, the trajectory with gaps over 2 hours left undrawn, routine places, and Together pairs
 * (04 sections 8.3, 8.4 and 8.6). It carries the investigative label on its face.
 */
export function PlacesMap({ layers, height = 360 }: { layers: PlacesMapLayers; height?: number }) {
  const { mapStyle, transformRequest, onMapError, onMapView, basemapNote } = useMapTheme()
  const bounds = useMemo(() => {
    const coords: [number, number][] = []
    for (const f of layers.dots?.features ?? []) coords.push(f.geometry.coordinates as [number, number])
    for (const f of layers.places?.features ?? []) coords.push(...(f.geometry.coordinates[0] as [number, number][]))
    for (const f of layers.pairs?.features ?? []) coords.push(...(f.geometry.coordinates as [number, number][]))
    return boundsOf(coords)
  }, [layers])
  const initial = bounds
    ? { bounds: [[bounds[0] - 0.002, bounds[1] - 0.002], [bounds[2] + 0.002, bounds[3] + 0.002]] as [[number, number], [number, number]] }
    : { longitude: 0, latitude: 20, zoom: 1 }
  return (
    <figure className="flex flex-col gap-1" aria-label="Places map">
      <div className="relative overflow-hidden rounded border" style={{ height }}>
        <Map
          key={bounds ? bounds.join(",") : "none"}
          initialViewState={initial}
          mapStyle={mapStyle}
          transformRequest={transformRequest}
          onError={onMapError}
          attributionControl={{ compact: true }}
          onLoad={(e) => { const c = e.target.getCenter(); onMapView(c.lng, c.lat) }}
          onMoveEnd={(e) => { const c = e.target.getCenter(); onMapView(c.lng, c.lat) }}
          style={{ width: "100%", height: "100%" }}
        >
          <NavigationControl position="top-right" showCompass={false} />
          <Source id="pm-places" type="geojson" data={layers.places ?? EMPTY}>
            <Layer id="pm-places-fill" type="fill" paint={{ "fill-color": "#7c3aed", "fill-opacity": 0.12 }} />
            <Layer id="pm-places-line" type="line" paint={{ "line-color": "#7c3aed", "line-width": 2 }} />
            <Layer id="pm-places-name" type="symbol" layout={{ "text-field": ["get", "name"], "text-size": 12 }}
              paint={{ "text-color": "#4c1d95", "text-halo-color": "#ffffff", "text-halo-width": 1 }} />
          </Source>
          <Source id="pm-areas" type="geojson" data={layers.areas ?? EMPTY}>
            <Layer id="pm-areas-fill" type="fill" paint={{ "fill-color": "#0284c7", "fill-opacity": 0.08 }} />
          </Source>
          <Source id="pm-lines" type="geojson" data={layers.lines ?? EMPTY}>
            <Layer id="pm-lines" type="line" paint={{ "line-color": "#0369a1", "line-width": 2, "line-opacity": 0.8 }} />
          </Source>
          <Source id="pm-pairs" type="geojson" data={layers.pairs ?? EMPTY}>
            <Layer id="pm-pairs" type="line" paint={{
              "line-width": 2,
              "line-color": ["match", ["get", "verdict"], "compatible", "#15803d", "separated", "#b91c1c", "#a16207"],
              "line-dasharray": [2, 1],
            }} />
          </Source>
          <Source id="pm-dots" type="geojson" data={layers.dots ?? EMPTY}>
            <Layer id="pm-dots" type="circle" paint={{
              "circle-radius": 4, "circle-color": "#0369a1", "circle-stroke-color": "#ffffff",
              "circle-stroke-width": ["match", ["get", "accuracy"], "not recorded", 0, 1.5],
              "circle-opacity": ["match", ["get", "accuracy"], "not recorded", 0.45, 0.9],
            }} />
          </Source>
          {basemapNote && <BasemapNote text={basemapNote} />}
          <div className="pointer-events-none absolute bottom-2 left-2 rounded bg-background/90 px-2 py-1 text-xs font-medium shadow">
            {PLACE_LABEL}
          </div>
        </Map>
      </div>
    </figure>
  )
}
