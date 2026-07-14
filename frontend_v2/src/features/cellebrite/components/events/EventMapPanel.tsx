import { useCallback, useEffect, useMemo, useRef } from "react"
import MaplibreMap, { Layer, NavigationControl, Source } from "react-map-gl/maplibre"
import maplibregl from "maplibre-gl"
import type { MapLayerMouseEvent, MapRef } from "react-map-gl/maplibre"
import "maplibre-gl/dist/maplibre-gl.css"

import { useMapTheme } from "@/features/map/hooks/use-map-theme"

import type { EventTrack, TimelineItem } from "../../types"
import { SmallEmpty } from "../shared/SmallEmpty"
import {
  EVENT_COLORS,
  eventKey,
  eventType,
  eventsWithinTrail,
  locationOf,
  reportKeyOf,
  trackPoints,
  trackReportKey,
} from "./eventUtils"

type PointFeature = GeoJSON.Feature<GeoJSON.Point, {
  key: string
  eventType: string
  reportKey: string
  reportColor: string
}>

export function EventMapPanel({
  events,
  tracks,
  playheadTime,
  trailWindowMs,
  isPlaying,
  selectedEventKey,
  colorByReport,
  active,
  onEventSelect,
}: {
  events: TimelineItem[]
  tracks: EventTrack[]
  playheadTime: Date | null
  trailWindowMs: number
  isPlaying: boolean
  selectedEventKey: string | null
  colorByReport: Map<string, string>
  active: boolean
  onEventSelect: (event: TimelineItem) => void
}) {
  const mapRef = useRef<MapRef | null>(null)
  const { styleUrl } = useMapTheme()
  const visibleEvents = useMemo(
    () => (isPlaying && playheadTime ? eventsWithinTrail(events, playheadTime, trailWindowMs) : events),
    [events, isPlaying, playheadTime, trailWindowMs]
  )

  const points = useMemo(() => {
    const features: PointFeature[] = visibleEvents
      .map((event) => {
        const location = locationOf(event)
        if (!location) return null
        return {
          type: "Feature" as const,
          properties: {
            key: eventKey(event),
            eventType: eventType(event),
            reportKey: reportKeyOf(event),
            reportColor: colorByReport.get(reportKeyOf(event)) ?? "#ffffff",
          },
          geometry: {
            type: "Point" as const,
            coordinates: [location.longitude, location.latitude],
          },
        }
      })
      .filter((feature): feature is PointFeature => Boolean(feature))
    return {
      type: "FeatureCollection" as const,
      features,
    }
  }, [colorByReport, visibleEvents])

  const trackLines = useMemo(() => {
    const features: GeoJSON.Feature<GeoJSON.LineString, { reportKey: string; color: string }>[] = []
    tracks.forEach((track) => {
      const points = trackPoints(track)
      if (points.length < 2) return
      const reportKey = trackReportKey(track)
      features.push({
        type: "Feature",
        properties: {
          reportKey,
          color: colorByReport.get(reportKey) ?? "#2563eb",
        },
        geometry: {
          type: "LineString",
          coordinates: points.map((point) => [point.longitude, point.latitude]),
        },
      })
    })
    return { type: "FeatureCollection" as const, features }
  }, [colorByReport, tracks])

  const selectedEvent = useMemo(
    () => events.find((event) => eventKey(event) === selectedEventKey) ?? null,
    [events, selectedEventKey]
  )

  const fitBounds = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const coordinates: [number, number][] = []
    points.features.forEach((feature) => coordinates.push(feature.geometry.coordinates as [number, number]))
    trackLines.features.forEach((feature) => feature.geometry.coordinates.forEach((coordinate) => coordinates.push(coordinate as [number, number])))
    if (coordinates.length === 0) return
    if (coordinates.length === 1) {
      map.flyTo({ center: coordinates[0], zoom: 12, duration: 0 })
      return
    }
    const lngs = coordinates.map((coordinate) => coordinate[0])
    const lats = coordinates.map((coordinate) => coordinate[1])
    map.fitBounds(
      [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ],
      { padding: 60, duration: 500, maxZoom: 14 }
    )
  }, [points.features, trackLines.features])

  useEffect(() => {
    if (!active) return
    const id = requestAnimationFrame(() => {
      mapRef.current?.resize()
      fitBounds()
    })
    return () => cancelAnimationFrame(id)
  }, [active, fitBounds])

  useEffect(() => {
    if (!selectedEvent || !mapRef.current) return
    const location = locationOf(selectedEvent)
    if (!location) return
    mapRef.current.flyTo({
      center: [location.longitude, location.latitude],
      zoom: Math.max(mapRef.current.getZoom(), 13),
      duration: 600,
    })
  }, [selectedEvent])

  const onClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const key = event.features?.[0]?.properties?.key
      if (!key) return
      const item = events.find((row) => eventKey(row) === key)
      if (item) onEventSelect(item)
    },
    [events, onEventSelect]
  )

  const onMouseMove = useCallback((event: MapLayerMouseEvent) => {
    const map = mapRef.current?.getMap()
    if (map) map.getCanvas().style.cursor = event.features?.length ? "pointer" : ""
  }, [])

  const onMouseLeave = useCallback(() => {
    const map = mapRef.current?.getMap()
    if (map) map.getCanvas().style.cursor = ""
  }, [])

  if (points.features.length === 0 && trackLines.features.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/20">
        <SmallEmpty label="No geolocated events in the current selection" />
      </div>
    )
  }

  return (
    <div className="relative h-full min-h-0">
      <MaplibreMap
        ref={mapRef}
        mapLib={maplibregl}
        mapStyle={styleUrl}
        initialViewState={{ longitude: -6.2603, latitude: 53.3498, zoom: 5 }}
        style={{ width: "100%", height: "100%" }}
        attributionControl={false}
        interactiveLayerIds={["event-points"]}
        onLoad={fitBounds}
        onClick={onClick}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        <NavigationControl position="top-right" showCompass={false} visualizePitch={false} />
        <Source id="event-track-source" type="geojson" data={trackLines}>
          <Layer
            id="event-track-line-halo"
            type="line"
            paint={{ "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.85 }}
          />
          <Layer
            id="event-track-line"
            type="line"
            paint={{
              "line-color": ["coalesce", ["get", "color"], "#2563eb"],
              "line-width": 4,
              "line-opacity": 0.9,
            }}
          />
        </Source>
        <Source id="event-point-source" type="geojson" data={points} cluster clusterRadius={45}>
          <Layer
            id="event-clusters"
            type="circle"
            filter={["has", "point_count"]}
            paint={{
              "circle-color": "#0c9da0",
              "circle-radius": ["step", ["get", "point_count"], 15, 25, 20, 100, 26],
              "circle-opacity": 0.85,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
            }}
          />
          <Layer
            id="event-cluster-count"
            type="symbol"
            filter={["has", "point_count"]}
            layout={{
              "text-field": ["get", "point_count_abbreviated"],
              "text-size": 11,
            }}
            paint={{ "text-color": "#0b202a" }}
          />
          <Layer
            id="event-points"
            type="circle"
            filter={["!", ["has", "point_count"]]}
            paint={{
              "circle-color": eventColorExpression() as unknown as string,
              "circle-radius": ["case", ["==", ["get", "key"], selectedEventKey ?? ""], 9, 6],
              "circle-stroke-color": ["coalesce", ["get", "reportColor"], "#ffffff"],
              "circle-stroke-width": ["case", ["==", ["get", "key"], selectedEventKey ?? ""], 4, 2],
              "circle-opacity": 0.9,
            }}
          />
        </Source>
      </MaplibreMap>
    </div>
  )
}

function eventColorExpression(): unknown[] {
  return [
    "match",
    ["get", "eventType"],
    ...Object.entries(EVENT_COLORS).flatMap(([type, color]) => [type, color]),
    "#64748b",
  ]
}
