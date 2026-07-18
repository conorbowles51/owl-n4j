import { useRef, useState, useCallback, useEffect, useMemo } from "react"
import Map, { Source, Layer, Marker, NavigationControl } from "react-map-gl/maplibre"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { MapPin } from "lucide-react"
import { useMapTheme } from "../hooks/use-map-theme"
import { useMapStore } from "../stores/map.store"
import { useGraphStore } from "@/stores/graph.store"
import { useMapAnalysis, type MapLocation } from "../hooks/use-map-data"
import { locationsToGeoJSON, createCircleGeoJSON } from "../lib/geojson"
import {
  pointLayer,
  heatmapLayer,
  proximityFillLayer,
  proximityOutlineLayer,
} from "../lib/map-styles"
import { EntityPopup } from "./EntityPopup"
import type { LocationCorrectionResult } from "@/features/graph/api"
import type { MapRef, MapLayerMouseEvent } from "react-map-gl/maplibre"

interface MapCanvasProps {
  caseId: string
  locations: MapLocation[]
}

interface LocationOverride {
  latitude: number
  longitude: number
  location_formatted?: string | null
  geocoding_confidence?: string | null
}

export function MapCanvas({ caseId, locations }: MapCanvasProps) {
  const mapRef = useRef<MapRef>(null)
  const { styleUrl } = useMapTheme()
  const { bounds } = useMapAnalysis(locations)

  // Hover state for popup
  const [hoveredLocationKey, setHoveredLocationKey] = useState<string | null>(null)
  const [previewLocation, setPreviewLocation] = useState<LocationOverride | null>(null)
  const [locationOverrides, setLocationOverrides] = useState<Record<string, LocationOverride>>({})
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showHeatmap = useMapStore((s) => s.showHeatmap)
  const hiddenTypes = useMapStore((s) => s.hiddenTypes)
  const proximityMode = useMapStore((s) => s.proximityMode)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const proximityRadius = useMapStore((s) => s.proximityRadius)
  const setProximityAnchor = useMapStore((s) => s.setProximityAnchor)
  const pendingFlyTo = useMapStore((s) => s.pendingFlyTo)
  const clearFlyTo = useMapStore((s) => s.clearFlyTo)
  const pendingZoomDelta = useMapStore((s) => s.pendingZoomDelta)
  const clearZoomDelta = useMapStore((s) => s.clearZoomDelta)
  const pendingFitBounds = useMapStore((s) => s.pendingFitBounds)
  const clearFitBounds = useMapStore((s) => s.clearFitBounds)

  // Graph store — selecting a marker selects the node for the shared detail panel
  const selectNodes = useGraphStore((s) => s.selectNodes)

  // GeoJSON data
  const effectiveLocations = useMemo(
    () =>
      locations.map((location) => {
        const override = locationOverrides[location.key]
        if (!override) return location
        return {
          ...location,
          latitude: override.latitude,
          longitude: override.longitude,
          location_formatted: override.location_formatted ?? location.location_formatted,
          geocoding_confidence: override.geocoding_confidence ?? location.geocoding_confidence,
        }
      }),
    [locations, locationOverrides]
  )

  const visibleLocations = useMemo(
    () => effectiveLocations.filter((l) => !hiddenTypes.has(l.type)),
    [effectiveLocations, hiddenTypes]
  )
  const geojson = useMemo(
    () => locationsToGeoJSON(visibleLocations),
    [visibleLocations]
  )

  // Proximity anchor
  const proximityAnchor = useMemo(
    () => effectiveLocations.find((l) => l.key === proximityAnchorKey) ?? null,
    [effectiveLocations, proximityAnchorKey]
  )

  // Proximity circle GeoJSON
  const proximityCircle = useMemo(() => {
    if (!proximityAnchor) return null
    return createCircleGeoJSON(
      [proximityAnchor.longitude, proximityAnchor.latitude],
      proximityRadius
    )
  }, [proximityAnchor, proximityRadius])

  // Hovered location for popup
  const hoveredLocation = useMemo(
    () => effectiveLocations.find((l) => l.key === hoveredLocationKey) ?? null,
    [effectiveLocations, hoveredLocationKey]
  )

  const resultToOverride = useCallback((result: LocationCorrectionResult): LocationOverride | null => {
    if (typeof result.latitude !== "number" || typeof result.longitude !== "number") {
      return null
    }
    return {
      latitude: result.latitude,
      longitude: result.longitude,
      location_formatted: result.formatted_address,
      geocoding_confidence: result.confidence,
    }
  }, [])

  const handleLocationPreview = useCallback(
    (_nodeKey: string, result: LocationCorrectionResult) => {
      const next = resultToOverride(result)
      setPreviewLocation(next)
      if (next && mapRef.current) {
        mapRef.current.flyTo({
          center: [next.longitude, next.latitude],
          zoom: Math.max(mapRef.current.getZoom(), 12),
          duration: 500,
        })
      }
    },
    [resultToOverride]
  )

  const handleLocationApplied = useCallback(
    (nodeKey: string, result: LocationCorrectionResult) => {
      const next = resultToOverride(result)
      setPreviewLocation(null)
      if (!next) return
      setLocationOverrides((current) => ({
        ...current,
        [nodeKey]: next,
      }))
    },
    [resultToOverride]
  )

  const handleLocationUndone = useCallback(
    (nodeKey: string, result: LocationCorrectionResult) => {
      const next = resultToOverride(result)
      setPreviewLocation(null)
      setLocationOverrides((current) => {
        const updated = { ...current }
        if (next) {
          updated[nodeKey] = next
        } else {
          delete updated[nodeKey]
        }
        return updated
      })
    },
    [resultToOverride]
  )

  // Sticky hover helpers
  const cancelHide = useCallback(() => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current)
      hideTimeoutRef.current = null
    }
  }, [])

  const startHide = useCallback(() => {
    cancelHide()
    hideTimeoutRef.current = setTimeout(() => {
      setHoveredLocationKey(null)
      setPreviewLocation(null)
      hideTimeoutRef.current = null
    }, 150)
  }, [cancelHide])

  // Clean up timeout on unmount
  useEffect(() => {
    return () => {
      if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current)
    }
  }, [])

  // Fit bounds on initial load
  const handleLoad = useCallback(() => {
    if (!bounds || !mapRef.current) return
    mapRef.current.fitBounds(
      [
        [bounds.minLng - 0.01, bounds.minLat - 0.01],
        [bounds.maxLng + 0.01, bounds.maxLat + 0.01],
      ],
      { padding: 60, duration: 1000 }
    )
  }, [bounds])

  // Handle pending fly-to
  useEffect(() => {
    if (!pendingFlyTo || !mapRef.current) return
    mapRef.current.flyTo({
      center: [pendingFlyTo.longitude, pendingFlyTo.latitude],
      zoom: pendingFlyTo.zoom ?? 14,
      duration: 1000,
    })
    clearFlyTo()
  }, [pendingFlyTo, clearFlyTo])

  // Handle pending zoom delta
  useEffect(() => {
    if (pendingZoomDelta === null || !mapRef.current) return
    if (pendingZoomDelta > 0) {
      mapRef.current.zoomIn({ duration: 300 })
    } else {
      mapRef.current.zoomOut({ duration: 300 })
    }
    clearZoomDelta()
  }, [pendingZoomDelta, clearZoomDelta])

  // Handle pending fit bounds
  useEffect(() => {
    if (!pendingFitBounds || !mapRef.current || !bounds) return
    mapRef.current.fitBounds(
      [
        [bounds.minLng - 0.01, bounds.minLat - 0.01],
        [bounds.maxLng + 0.01, bounds.maxLat + 0.01],
      ],
      { padding: 60, duration: 1000 }
    )
    clearFitBounds()
  }, [pendingFitBounds, clearFitBounds, bounds])

  // Hover handler — show popup on hover over unclustered points
  const handleMouseMove = useCallback(
    (e: MapLayerMouseEvent) => {
      const map = mapRef.current?.getMap()
      if (!map) return

      const features = map.queryRenderedFeatures(e.point, {
        layers: ["unclustered-point"],
      })

      if (features.length > 0) {
        const key = features[0].properties?.key as string | undefined
        if (key) {
          cancelHide()
          if (hoveredLocationKey !== key) setPreviewLocation(null)
          setHoveredLocationKey(key)
          map.getCanvas().style.cursor = "pointer"
          return
        }
      }

      map.getCanvas().style.cursor = "default"
      startHide()
    },
    [cancelHide, hoveredLocationKey, startHide]
  )

  const handleMouseLeave = useCallback(() => {
    startHide()
  }, [startHide])

  // Click handlers
  const handleClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const map = mapRef.current?.getMap()
      if (!map) return

      // Check for point click
      const pointFeatures = map.queryRenderedFeatures(e.point, {
        layers: ["unclustered-point"],
      })
      if (pointFeatures.length > 0) {
        const key = pointFeatures[0].properties?.key
        if (key) {
          if (proximityMode && !proximityAnchorKey) {
            setProximityAnchor(key)
          } else {
            selectNodes([key])
          }
          return
        }
      }

      // Click on empty space — deselect
      selectNodes([])
    },
    [selectNodes, proximityMode, proximityAnchorKey, setProximityAnchor]
  )

  return (
    <Map
      ref={mapRef}
      mapLib={maplibregl}
      mapStyle={styleUrl}
      style={{ width: "100%", height: "100%" }}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onLoad={handleLoad}
      attributionControl={false}
      interactiveLayerIds={["unclustered-point"]}
    >
      <NavigationControl position="top-right" showCompass={false} visualizePitch={false} />

      {/* Main data source */}
      <Source id="locations" type="geojson" data={geojson}>
        {/* Heatmap (below markers) */}
        {showHeatmap && <Layer {...heatmapLayer} />}

        {/* Individual points */}
        <Layer {...pointLayer} />
      </Source>

      {/* Proximity circle */}
      {proximityCircle && (
        <Source id="proximity-circle" type="geojson" data={proximityCircle}>
          <Layer {...proximityFillLayer} />
          <Layer {...proximityOutlineLayer} />
        </Source>
      )}

      {previewLocation && (
        <Marker
          latitude={previewLocation.latitude}
          longitude={previewLocation.longitude}
          anchor="bottom"
        >
          <MapPin className="size-8 fill-amber-500 text-amber-800 drop-shadow" />
        </Marker>
      )}

      {/* Hovered entity popup */}
      {hoveredLocation && (
        <EntityPopup
          caseId={caseId}
          location={hoveredLocation}
          onClose={() => {
            setHoveredLocationKey(null)
            setPreviewLocation(null)
          }}
          onSetProximityAnchor={(key) => {
            setProximityAnchor(key)
          }}
          onMouseEnter={cancelHide}
          onMouseLeave={startHide}
          onLocationPreview={(result) => handleLocationPreview(hoveredLocation.key, result)}
          onLocationApplied={(result) => handleLocationApplied(hoveredLocation.key, result)}
          onLocationUndone={(result) => handleLocationUndone(hoveredLocation.key, result)}
        />
      )}
    </Map>
  )
}
