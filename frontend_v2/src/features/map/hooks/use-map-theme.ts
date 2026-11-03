import { useCallback, useMemo, useState } from "react"
import type { ErrorEvent as MapErrorEvent } from "react-map-gl/maplibre"
import {
  basemapCoverage,
  outsideCoverage,
  BASEMAP_PATH,
  BASEMAP_SOURCE_ID,
  basemapTransformRequest,
  buildBasemapStyle,
  ensureBasemapProtocol,
} from "../lib/basemap-style"

function isDarkMode(): boolean {
  return document.documentElement.classList.contains("dark")
}

/** The note shown on the map when the base map held on this server cannot be read. */
export const BASEMAP_UNAVAILABLE_NOTE = "Base map could not be loaded from this server; the points are still placed."
export const BASEMAP_NOT_HELD_NOTE = "Detailed map not held on this server for this area"

function isBasemapError(event: MapErrorEvent): boolean {
  const e = event as MapErrorEvent & { sourceId?: string }
  if (e.sourceId === BASEMAP_SOURCE_ID) return true
  const message = String(e.error?.message ?? "")
  return message.includes(`${BASEMAP_PATH}/`)
}

/** The base map style (held on this server, light or dark with the page) and what a map needs to load it. */
export function useMapTheme() {
  const isDark = useMemo(() => isDarkMode(), [])
  const mapStyle = useMemo(() => {
    ensureBasemapProtocol(window.location.origin)
    return buildBasemapStyle(isDark, window.location.origin)
  }, [isDark])
  const [failed, setFailed] = useState(false)
  const [notHeld, setNotHeld] = useState(false)
  const onMapError = useCallback((event: MapErrorEvent) => {
    if (isBasemapError(event)) setFailed(true)
  }, [])
  /** Call with the view centre after the map loads or moves. */
  const onMapView = useCallback((lng: number, lat: number) => {
    void basemapCoverage().then((coverage) => setNotHeld(outsideCoverage(coverage, lng, lat)))
  }, [])
  const basemapNote = failed ? BASEMAP_UNAVAILABLE_NOTE : notHeld ? BASEMAP_NOT_HELD_NOTE : null

  return { mapStyle, isDark, transformRequest: basemapTransformRequest, onMapError, onMapView, basemapNote }
}
