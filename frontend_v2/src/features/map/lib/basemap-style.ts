import maplibregl from "maplibre-gl"
import type { RequestParameters, StyleSpecification } from "maplibre-gl"
import { BLACK, GRAYSCALE, layers, type Flavor } from "@protomaps/basemaps"
import { FetchSource, PMTiles, Protocol } from "pmtiles"

/**
 * The base map is held on this server: one PMTiles file of the world (deploy/refresh-basemap.sh) and the fonts and
 * symbols its labels use, served by nginx under /basemap/ behind the app's sign-in. No style, tile, font or symbol
 * is fetched from an outside map service, so no outside service learns which places an investigator looks at.
 */
export const BASEMAP_PATH = "/basemap"
export const BASEMAP_SOURCE_ID = "protomaps"
const ARCHIVE_FILE = "world.pmtiles"

/** Colours of the map Loupe drew before (Carto Positron and Dark Matter), laid over the nearest Protomaps flavors. */
const LIGHT_FLAVOR: Flavor = {
  ...GRAYSCALE,
  background: "#fafaf8",
  earth: "#fafaf8",
  water: "#d4dadc",
}

const DARK_FLAVOR: Flavor = {
  ...BLACK,
  background: "#0e0e0e",
  earth: "#0e0e0e",
  water: "#2c353c",
}

export function basemapArchiveUrl(origin: string): string {
  return `${origin}${BASEMAP_PATH}/${ARCHIVE_FILE}`
}

/** The light or dark style, every URL on `origin` (the page's own address). */
export function buildBasemapStyle(isDark: boolean, origin: string): StyleSpecification {
  const flavor = isDark ? DARK_FLAVOR : LIGHT_FLAVOR
  const spriteName = isDark ? "black" : "grayscale"
  return {
    version: 8,
    glyphs: `${origin}${BASEMAP_PATH}/assets/fonts/{fontstack}/{range}.pbf`,
    sprite: `${origin}${BASEMAP_PATH}/assets/sprites/v4/${spriteName}`,
    sources: {
      [BASEMAP_SOURCE_ID]: {
        type: "vector",
        url: `pmtiles://${basemapArchiveUrl(origin)}`,
        attribution: '<a href="https://openstreetmap.org/copyright">© OpenStreetMap</a> · Protomaps',
      },
    },
    layers: layers(BASEMAP_SOURCE_ID, flavor, { lang: "en" }) as StyleSpecification["layers"],
  }
}

let protocol: Protocol | null = null
let archiveSource: FetchSource | null = null
let archive: PMTiles | null = null

/** The area the held file covers ([west, south, east, north]), read from the file's own header; null if unreadable. */
export async function basemapCoverage(): Promise<[number, number, number, number] | null> {
  if (!archive) return null
  try {
    const h = await archive.getHeader()
    return [h.minLon, h.minLat, h.maxLon, h.maxLat]
  } catch {
    return null
  }
}

/** Whether a view centre falls outside the held area (the note "Detailed map not held on this server for this area"). */
export function outsideCoverage(
  coverage: [number, number, number, number] | null,
  lng: number,
  lat: number,
): boolean {
  if (!coverage) return false
  const [w, s, e, n] = coverage
  const x = ((((lng + 180) % 360) + 360) % 360) - 180
  return x < w || x > e || lat < s || lat > n
}

/**
 * Registers the pmtiles:// protocol with MapLibre once. The archive's requests carry the sign-in cookie.
 */
export function ensureBasemapProtocol(origin: string = window.location.origin): void {
  const url = basemapArchiveUrl(origin)
  if (!protocol) {
    protocol = new Protocol()
    maplibregl.addProtocol("pmtiles", protocol.tile)
  }
  if (!archiveSource || archiveSource.url !== url) {
    archiveSource = new FetchSource(url)
    archive = new PMTiles(archiveSource)
    protocol.add(archive)
  }
}

/** MapLibre's transformRequest: the fonts and symbols under /basemap/ go with the sign-in cookie. */
export function basemapTransformRequest(url: string): RequestParameters {
  return { url }
}

/** Every http(s) URL in a style object (the sources, glyphs and sprite), for the check that none leaves the box. */
export function styleUrls(style: unknown): string[] {
  const found: string[] = []
  const walk = (value: unknown) => {
    if (typeof value === "string") {
      const match = value.match(/^(?:pmtiles:\/\/)?(https?:\/\/[^\s"']+)/)
      if (match) found.push(match[1])
    } else if (Array.isArray(value)) {
      value.forEach(walk)
    } else if (value && typeof value === "object") {
      for (const [key, inner] of Object.entries(value)) {
        if (key === "attribution") continue
        walk(inner)
      }
    }
  }
  walk(style)
  return found
}
