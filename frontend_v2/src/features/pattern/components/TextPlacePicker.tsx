import { useEffect, useMemo, useRef } from "react"
import Map, { Layer, NavigationControl, Source, type MapRef } from "react-map-gl/maplibre"
import "maplibre-gl/dist/maplibre-gl.css"
import type { Feature, FeatureCollection, Point, Polygon } from "geojson"
import { useMapTheme } from "@/features/map/hooks/use-map-theme"
import { BasemapNote } from "@/features/map/components/BasemapNote"
import { circlePolygon } from "../text-places-lib"

export interface PickerPoint { lat: number; lon: number }

/**
 * The case map's base map (use-map-theme, BasemapNote) for placing one written place: a click sets the point, the
 * radius is drawn around it, and the suggestions (if any) show as hollow markers labelled as suggestions. Loaded
 * only when a person opens "Place on map", so the map code never loads with the list.
 */
export default function TextPlacePicker({ point, radiusM, suggestions, onPick, height = 300 }: {
  point: PickerPoint | null
  radiusM: number
  suggestions: { lat: number; lon: number; name: string }[]
  onPick: (p: PickerPoint) => void
  height?: number
}) {
  const { mapStyle, transformRequest, onMapError, onMapView, basemapNote } = useMapTheme()
  const mapRef = useRef<MapRef>(null)
  // the map follows the point (a click, a suggestion chosen, coordinates typed): zoomed in far enough to see the
  // radius, and never moved when the point is already in view at that zoom
  useEffect(() => {
    const m = mapRef.current
    if (!m || !point) return
    const inView = m.getBounds()?.contains([point.lon, point.lat])
    if (inView && m.getZoom() >= 11) return
    m.flyTo({ center: [point.lon, point.lat], zoom: Math.max(m.getZoom(), radiusM > 5000 ? 10 : 13), duration: 600 })
  }, [point?.lat, point?.lon]) // eslint-disable-line react-hooks/exhaustive-deps
  const dot = useMemo<FeatureCollection<Point>>(() => ({
    type: "FeatureCollection",
    features: point ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [point.lon, point.lat] } }] : [],
  }), [point])
  const area = useMemo<FeatureCollection<Polygon>>(() => ({
    type: "FeatureCollection",
    features: point && radiusM > 0 ? [circlePolygon(point.lat, point.lon, radiusM)] : [],
  }), [point, radiusM])
  const sugg = useMemo<FeatureCollection<Point>>(() => ({
    type: "FeatureCollection",
    features: suggestions.map((s): Feature<Point> => ({
      type: "Feature", properties: { name: `${s.name} (suggested)` },
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
    })),
  }), [suggestions])
  const centre = point ?? suggestions[0] ?? null
  const initial = centre ? { longitude: centre.lon, latitude: centre.lat, zoom: point ? 13 : 9 }
    : { longitude: 0, latitude: 20, zoom: 1 }
  return (
    <figure className="flex flex-col gap-1" aria-label="Place on map">
      <div className="relative overflow-hidden rounded border" style={{ height }}>
        <Map
          ref={mapRef}
          initialViewState={initial}
          mapStyle={mapStyle}
          transformRequest={transformRequest}
          onError={onMapError}
          attributionControl={{ compact: true }}
          cursor="crosshair"
          onLoad={(e) => { const c = e.target.getCenter(); onMapView(c.lng, c.lat) }}
          onMoveEnd={(e) => { const c = e.target.getCenter(); onMapView(c.lng, c.lat) }}
          onClick={(e) => onPick({ lat: Number(e.lngLat.lat.toFixed(6)), lon: Number(e.lngLat.lng.toFixed(6)) })}
          style={{ width: "100%", height: "100%" }}
        >
          <NavigationControl position="top-right" showCompass={false} />
          <Source id="tp-suggestions" type="geojson" data={sugg}>
            <Layer id="tp-suggestions" type="circle" paint={{
              "circle-radius": 6, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#a16207", "circle-stroke-width": 2,
            }} />
            <Layer id="tp-suggestions-name" type="symbol" layout={{ "text-field": ["get", "name"], "text-font": ["Noto Sans Medium"], "text-size": 11, "text-offset": [0, 1.2] }}
              paint={{ "text-color": "#713f12", "text-halo-color": "#ffffff", "text-halo-width": 1 }} />
          </Source>
          <Source id="tp-area" type="geojson" data={area}>
            <Layer id="tp-area-fill" type="fill" paint={{ "fill-color": "#7c3aed", "fill-opacity": 0.15 }} />
            <Layer id="tp-area-line" type="line" paint={{ "line-color": "#7c3aed", "line-width": 2 }} />
          </Source>
          <Source id="tp-point" type="geojson" data={dot}>
            <Layer id="tp-point" type="circle" paint={{
              "circle-radius": 5, "circle-color": "#7c3aed", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2,
            }} />
          </Source>
          {basemapNote && <BasemapNote text={basemapNote} />}
        </Map>
      </div>
      <figcaption className="text-xs text-muted-foreground">
        Click the map to set the point. Hollow markers are suggestions from the offline place list, not confirmed.
      </figcaption>
    </figure>
  )
}
