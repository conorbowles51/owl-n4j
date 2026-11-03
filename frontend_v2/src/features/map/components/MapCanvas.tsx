import { useRef, useState, useCallback, useEffect, useMemo } from "react"
import Map, { Source, Layer, NavigationControl } from "react-map-gl/maplibre"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { useMapTheme } from "../hooks/use-map-theme"
import { useMapStore } from "../stores/map.store"
import { useGraphStore } from "@/stores/graph.store"
import { useMapAnalysis, type MapLocation } from "../hooks/use-map-data"
import {
  boundingShapesToGeoJSON,
  createCircleGeoJSON,
  drawingLineToGeoJSON,
  drawingPointsToGeoJSON,
  drawingPolygonPreviewToGeoJSON,
  locationsToGeoJSON,
} from "../lib/geojson"
import {
  approximateLocationAreaLayer,
  approximateLocationOutlineLayer,
  boundingShapeFillLayer,
  boundingShapeOutlineLayer,
  draftBoundingShapeFillLayer,
  draftBoundingShapeOutlineLayer,
  drawingLineLayer,
  drawingPointLayer,
  drawingShapeFillLayer,
  drawingShapeOutlineLayer,
  pointLayer,
  heatmapLayer,
  proximityFillLayer,
  proximityOutlineLayer,
} from "../lib/map-styles"
import { getVisibleLocations } from "../lib/visible-locations"
import { boundsToClosedRing, viewBox, type LngLatPoint } from "../lib/geometry"
import { EntityPopup } from "./EntityPopup"
import { BasemapNote } from "./BasemapNote"
import type { MapRef, MapLayerMouseEvent } from "react-map-gl/maplibre"
import type { PhoneMapItem } from "@/features/phones/api"
import { accuracyPixelsAtZoom20 } from "./map-accuracy"

interface MapCanvasProps {
  locations: MapLocation[]
  /** The phone layer's points and clusters (03 section 13), drawn apart from graph locations. */
  phoneItems?: PhoneMapItem[]
  /** Called with the viewport [w, s, e, n] and zoom after the map moves. */
  onView?: (bbox: number[], zoom: number) => void
  /** Fit to this [w, s, e, n] once when there are no graph locations to fit to. */
  fitTo?: number[] | null
}

const LOCATION_INTERACTIVE_LAYER_IDS = [
  "unclustered-point",
  "approximate-location-outline",
  "approximate-location-area",
]

interface ScreenPoint {
  x: number
  y: number
}

interface BoxDragState {
  startLngLat: LngLatPoint
  startPoint: ScreenPoint
}

interface SecondaryPanState {
  lastPoint: ScreenPoint
}

const BOX_DRAW_MIN_PIXELS = 8

function getEventPoint(e: MapLayerMouseEvent): ScreenPoint {
  return {
    x: e.originalEvent.clientX,
    y: e.originalEvent.clientY,
  }
}

function getLngLatPoint(e: MapLayerMouseEvent): LngLatPoint {
  return [e.lngLat.lng, e.lngLat.lat]
}

function getPointDistance(a: ScreenPoint, b: ScreenPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

export function MapCanvas({ locations, phoneItems, onView, fitTo }: MapCanvasProps) {
  const mapRef = useRef<MapRef>(null)
  const boxDragRef = useRef<BoxDragState | null>(null)
  const secondaryPanRef = useRef<SecondaryPanState | null>(null)
  const { mapStyle, transformRequest, onMapError, onMapView, basemapNote } = useMapTheme()
  const { bounds } = useMapAnalysis(locations)

  // Hover state for popup
  const [hoveredLocationKey, setHoveredLocationKey] = useState<string | null>(
    null
  )
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showHeatmap = useMapStore((s) => s.showHeatmap)
  const hiddenTypes = useMapStore((s) => s.hiddenTypes)
  const hiddenConfidenceTiers = useMapStore((s) => s.hiddenConfidenceTiers)
  const needsReviewMode = useMapStore((s) => s.needsReviewMode)
  const proximityMode = useMapStore((s) => s.proximityMode)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const proximityRadius = useMapStore((s) => s.proximityRadius)
  const setProximityAnchor = useMapStore((s) => s.setProximityAnchor)
  const drawMode = useMapStore((s) => s.drawMode)
  const drawTool = useMapStore((s) => s.drawTool)
  const drawingPoints = useMapStore((s) => s.drawingPoints)
  const draftBoundingShapes = useMapStore((s) => s.draftBoundingShapes)
  const boundingShapes = useMapStore((s) => s.boundingShapes)
  const setDrawingPoints = useMapStore((s) => s.setDrawingPoints)
  const addDrawingPoint = useMapStore((s) => s.addDrawingPoint)
  const finishDraftShape = useMapStore((s) => s.finishDraftShape)
  const finishDrawingShape = useMapStore((s) => s.finishDrawingShape)
  const pendingFlyTo = useMapStore((s) => s.pendingFlyTo)
  const clearFlyTo = useMapStore((s) => s.clearFlyTo)
  const pendingZoomDelta = useMapStore((s) => s.pendingZoomDelta)
  const clearZoomDelta = useMapStore((s) => s.clearZoomDelta)
  const pendingFitBounds = useMapStore((s) => s.pendingFitBounds)
  const clearFitBounds = useMapStore((s) => s.clearFitBounds)

  // Graph store — selecting a marker selects the node for the shared detail panel
  const selectNodes = useGraphStore((s) => s.selectNodes)

  // GeoJSON data
  const visibleLocations = useMemo(
    () =>
      getVisibleLocations(locations, {
        hiddenTypes,
        hiddenConfidenceTiers,
        needsReviewMode,
        boundingShapes,
      }),
    [
      locations,
      hiddenTypes,
      hiddenConfidenceTiers,
      needsReviewMode,
      boundingShapes,
    ]
  )
  const geojson = useMemo(
    () => locationsToGeoJSON(visibleLocations),
    [visibleLocations]
  )
  const boundingShapesGeoJSON = useMemo(
    () => boundingShapesToGeoJSON(boundingShapes),
    [boundingShapes]
  )
  const draftBoundingShapesGeoJSON = useMemo(
    () => boundingShapesToGeoJSON(draftBoundingShapes),
    [draftBoundingShapes]
  )
  const drawingLineGeoJSON = useMemo(
    () => drawingLineToGeoJSON(drawingPoints),
    [drawingPoints]
  )
  const drawingPolygonPreviewGeoJSON = useMemo(
    () => drawingPolygonPreviewToGeoJSON(drawingPoints),
    [drawingPoints]
  )
  const drawingPointsGeoJSON = useMemo(
    () => drawingPointsToGeoJSON(drawTool === "polygon" ? drawingPoints : []),
    [drawTool, drawingPoints]
  )

  // Proximity anchor
  const proximityAnchor = useMemo(
    () => locations.find((l) => l.key === proximityAnchorKey) ?? null,
    [locations, proximityAnchorKey]
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
    () => locations.find((l) => l.key === hoveredLocationKey) ?? null,
    [locations, hoveredLocationKey]
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
      hideTimeoutRef.current = null
    }, 150)
  }, [cancelHide])

  // Clean up timeout on unmount
  useEffect(() => {
    return () => {
      if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current)
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current?.getMap()
    if (!map) return

    map.getCanvas().style.cursor = drawMode ? "crosshair" : "default"
    if (!drawMode) {
      boxDragRef.current = null
      secondaryPanRef.current = null
    }
  }, [drawMode])

  useEffect(() => {
    if (!drawMode) return

    const handleWindowMouseUp = (event: MouseEvent) => {
      if (event.button === 2 && secondaryPanRef.current) {
        secondaryPanRef.current = null
        mapRef.current
          ?.getMap()
          .getCanvas()
          .style.setProperty("cursor", "crosshair")
      }

      if (event.button === 0 && boxDragRef.current) {
        // Release landed off the map canvas — commit the box instead of
        // silently dropping it
        const boxDrag = boxDragRef.current
        boxDragRef.current = null
        const map = mapRef.current?.getMap()
        const releasePoint = { x: event.clientX, y: event.clientY }
        if (
          map &&
          getPointDistance(boxDrag.startPoint, releasePoint) >=
            BOX_DRAW_MIN_PIXELS
        ) {
          const rect = map.getCanvas().getBoundingClientRect()
          const { lng, lat } = map.unproject([
            releasePoint.x - rect.left,
            releasePoint.y - rect.top,
          ])
          finishDraftShape(boundsToClosedRing(boxDrag.startLngLat, [lng, lat]))
        } else {
          setDrawingPoints([])
        }
      }
    }

    window.addEventListener("mouseup", handleWindowMouseUp)
    return () => window.removeEventListener("mouseup", handleWindowMouseUp)
  }, [drawMode, finishDraftShape, setDrawingPoints])

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

      if (drawMode) {
        if (secondaryPanRef.current) {
          e.originalEvent.preventDefault()
          const point = getEventPoint(e)
          const dx = point.x - secondaryPanRef.current.lastPoint.x
          const dy = point.y - secondaryPanRef.current.lastPoint.y
          // panBy shifts the CENTER by the offset, so the content moves opposite
          // the cursor; negate so the map follows the drag like native panning.
          map.panBy([-dx, -dy], { duration: 0 })
          secondaryPanRef.current = { lastPoint: point }
          map.getCanvas().style.cursor = "grabbing"
          return
        }

        if (drawTool === "box" && boxDragRef.current) {
          e.originalEvent.preventDefault()
          setDrawingPoints(
            boundsToClosedRing(
              boxDragRef.current.startLngLat,
              getLngLatPoint(e)
            )
          )
        }

        map.getCanvas().style.cursor = "crosshair"
        setHoveredLocationKey(null)
        return
      }

      const features = map.queryRenderedFeatures(e.point, {
        layers: LOCATION_INTERACTIVE_LAYER_IDS,
      })

      if (features.length > 0) {
        const key = features[0].properties?.key as string | undefined
        if (key) {
          cancelHide()
          setHoveredLocationKey(key)
          map.getCanvas().style.cursor = "pointer"
          return
        }
      }

      map.getCanvas().style.cursor = "default"
      startHide()
    },
    [cancelHide, drawMode, drawTool, setDrawingPoints, startHide]
  )

  const handleMouseLeave = useCallback(() => {
    if (drawMode && secondaryPanRef.current) return
    startHide()
  }, [drawMode, startHide])

  const handleMouseDown = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!drawMode) return

      e.originalEvent.preventDefault()
      setHoveredLocationKey(null)

      if (e.originalEvent.button === 2) {
        secondaryPanRef.current = { lastPoint: getEventPoint(e) }
        mapRef.current
          ?.getMap()
          .getCanvas()
          .style.setProperty("cursor", "grabbing")
        return
      }

      if (e.originalEvent.button !== 0) return

      if (drawTool === "box") {
        const startLngLat = getLngLatPoint(e)
        boxDragRef.current = {
          startLngLat,
          startPoint: getEventPoint(e),
        }
        setDrawingPoints([])
      }
    },
    [drawMode, drawTool, setDrawingPoints]
  )

  const handleMouseUp = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!drawMode) return

      if (e.originalEvent.button === 2 && secondaryPanRef.current) {
        e.originalEvent.preventDefault()
        secondaryPanRef.current = null
        mapRef.current
          ?.getMap()
          .getCanvas()
          .style.setProperty("cursor", "crosshair")
        return
      }

      if (
        e.originalEvent.button === 0 &&
        drawTool === "box" &&
        boxDragRef.current
      ) {
        e.originalEvent.preventDefault()
        const boxDrag = boxDragRef.current
        boxDragRef.current = null

        if (
          getPointDistance(boxDrag.startPoint, getEventPoint(e)) <
          BOX_DRAW_MIN_PIXELS
        ) {
          setDrawingPoints([])
          return
        }

        finishDraftShape(
          boundsToClosedRing(boxDrag.startLngLat, getLngLatPoint(e))
        )
      }
    },
    [drawMode, drawTool, finishDraftShape, setDrawingPoints]
  )

  const handleContextMenu = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!drawMode) return
      e.originalEvent.preventDefault()
    },
    [drawMode]
  )

  // Double-click closes an in-progress polygon — the standard map-drawing
  // gesture, alongside the toolbar's Finish button.
  const handleDblClick = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!drawMode) return
      e.preventDefault()
      if (drawTool === "polygon") finishDrawingShape()
    },
    [drawMode, drawTool, finishDrawingShape]
  )

  // Click handlers
  const handleClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const map = mapRef.current?.getMap()
      if (!map) return

      if (drawMode) {
        if (drawTool === "polygon") {
          addDrawingPoint(getLngLatPoint(e))
        }
        setHoveredLocationKey(null)
        return
      }

      // Check for exact pin or approximate area click
      const locationFeatures = map.queryRenderedFeatures(e.point, {
        layers: LOCATION_INTERACTIVE_LAYER_IDS,
      })
      if (locationFeatures.length > 0) {
        const key = locationFeatures[0].properties?.key
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
    [
      addDrawingPoint,
      drawMode,
      drawTool,
      selectNodes,
      proximityMode,
      proximityAnchorKey,
      setProximityAnchor,
    ]
  )

  return (
    <Map
      ref={mapRef}
      mapLib={maplibregl}
      mapStyle={mapStyle}
      transformRequest={transformRequest}
      onError={onMapError}
      style={{ width: "100%", height: "100%" }}
      dragPan={!drawMode}
      dragRotate={!drawMode}
      doubleClickZoom={!drawMode}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onClick={handleClick}
      onDblClick={handleDblClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onContextMenu={handleContextMenu}
      onLoad={(e) => {
        handleLoad()
        const map = e.target
        if (fitTo && locations.length === 0) {
          const [w, s, ea, n] = fitTo
          map.fitBounds([[w, s], [ea === w ? ea + 0.01 : ea, n === s ? n + 0.01 : n]], { padding: 60, maxZoom: 15, duration: 0 })
        }
        onView?.(viewBox(map.getBounds()), map.getZoom())
        onMapView(map.getCenter().lng, map.getCenter().lat)
      }}
      onMoveEnd={(e) => {
        onView?.(viewBox(e.target.getBounds()), e.target.getZoom())
        onMapView(e.target.getCenter().lng, e.target.getCenter().lat)
      }}
      attributionControl={{ compact: true }}
      interactiveLayerIds={drawMode ? [] : LOCATION_INTERACTIVE_LAYER_IDS}
    >
      <NavigationControl
        position="top-right"
        showCompass={false}
        visualizePitch={false}
      />

      {/* Committed bounding filters */}
      {boundingShapesGeoJSON.features.length > 0 && (
        <Source
          id="bounding-shapes"
          type="geojson"
          data={boundingShapesGeoJSON}
        >
          <Layer {...boundingShapeFillLayer} />
          <Layer {...boundingShapeOutlineLayer} />
        </Source>
      )}

      {/* Pending bounding filters */}
      {draftBoundingShapesGeoJSON.features.length > 0 && (
        <Source
          id="draft-bounding-shapes"
          type="geojson"
          data={draftBoundingShapesGeoJSON}
        >
          <Layer {...draftBoundingShapeFillLayer} />
          <Layer {...draftBoundingShapeOutlineLayer} />
        </Source>
      )}

      {/* In-progress bounding shape */}
      {drawingPolygonPreviewGeoJSON && (
        <Source
          id="drawing-shape-preview"
          type="geojson"
          data={drawingPolygonPreviewGeoJSON}
        >
          <Layer {...drawingShapeFillLayer} />
          <Layer {...drawingShapeOutlineLayer} />
        </Source>
      )}
      {drawingLineGeoJSON && (
        <Source
          id="drawing-shape-line"
          type="geojson"
          data={drawingLineGeoJSON}
        >
          <Layer {...drawingLineLayer} />
        </Source>
      )}
      {drawingPointsGeoJSON.features.length > 0 && (
        <Source
          id="drawing-shape-points"
          type="geojson"
          data={drawingPointsGeoJSON}
        >
          <Layer {...drawingPointLayer} />
        </Source>
      )}

      {/* Main data source */}
      <Source id="locations" type="geojson" data={geojson}>
        {/* Heatmap (below markers) */}
        {showHeatmap && <Layer {...heatmapLayer} />}

        {/* Approximate locations */}
        <Layer {...approximateLocationAreaLayer} />
        <Layer {...approximateLocationOutlineLayer} />

        {/* Individual points */}
        <Layer {...pointLayer} />
      </Source>

      {/* Phone layer (03 section 13.3): a radius when accuracy is known, a dashed-looking hollow ring when not */}
      {phoneItems && phoneItems.length > 0 && (
        <Source id="phone-points" type="geojson" data={phoneGeoJSON(phoneItems)}>
          <Layer id="phone-accuracy" type="circle" filter={["==", ["get", "has_accuracy"], true]} paint={{
            // the reported accuracy in screen pixels: metres per pixel on 512-pixel tiles, corrected for latitude
            "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 0, ["/", ["get", "r20"], 1048576], 20, ["get", "r20"]],
            "circle-color": "#2563eb", "circle-opacity": 0.12, "circle-stroke-color": "#2563eb", "circle-stroke-width": 1,
          }} />
          <Layer id="phone-point" type="circle" filter={["==", ["get", "kind"], "point"]} paint={{
            "circle-radius": 5,
            "circle-color": ["case", ["get", "has_accuracy"], "#2563eb", "rgba(0,0,0,0)"],
            "circle-stroke-color": "#2563eb", "circle-stroke-width": ["case", ["get", "has_accuracy"], 1, 2],
            "circle-stroke-opacity": ["case", ["get", "has_accuracy"], 1, 0.7],
          }} />
          <Layer id="phone-cluster" type="circle" filter={["==", ["get", "kind"], "cluster"]} paint={{
            "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 10, 1000, 24],
            "circle-color": "#2563eb", "circle-opacity": 0.6,
          }} />
          <Layer id="phone-cluster-count" type="symbol" filter={["==", ["get", "kind"], "cluster"]} layout={{ "text-field": ["get", "label"], "text-font": ["Noto Sans Regular"], "text-size": 11 }} paint={{ "text-color": "#fff" }} />
        </Source>
      )}

      {/* Proximity circle */}
      {proximityCircle && (
        <Source id="proximity-circle" type="geojson" data={proximityCircle}>
          <Layer {...proximityFillLayer} />
          <Layer {...proximityOutlineLayer} />
        </Source>
      )}

      {/* Hovered entity popup */}
      {hoveredLocation && (
        <EntityPopup
          location={hoveredLocation}
          onClose={() => setHoveredLocationKey(null)}
          onSetProximityAnchor={(key) => {
            setProximityAnchor(key)
          }}
          onMouseEnter={cancelHide}
          onMouseLeave={startHide}
        />
      )}

      {basemapNote && <BasemapNote text={basemapNote} />}
    </Map>
  )
}

function phoneGeoJSON(items: PhoneMapItem[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: items.map((i) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [i.lon, i.lat] },
      properties: i.type === "point"
        ? { kind: "point", has_accuracy: i.accuracy_m !== null, accuracy_m: i.accuracy_m ?? 0, r20: accuracyPixelsAtZoom20(i.accuracy_m ?? 0, i.lat), label: i.phone_label }
        : { kind: "cluster", has_accuracy: false, count: i.count, label: i.count.toLocaleString("en-US") },
    })),
  }
}
