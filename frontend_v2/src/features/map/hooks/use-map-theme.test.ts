import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const { addProtocol } = vi.hoisted(() => ({ addProtocol: vi.fn() }))
vi.mock("maplibre-gl", () => ({ default: { addProtocol } }))

import { useMapTheme } from "./use-map-theme"
import { buildBasemapStyle, outsideCoverage, styleUrls } from "../lib/basemap-style"

/** Every http(s) URL anywhere in a value (strings, arrays, objects), whatever field holds it. */
function allUrls(value: unknown): string[] {
  return JSON.stringify(value ?? null).match(/https?:\/\/[^\s"'\\]+/g) ?? []
}

function offBox(urls: string[], origin: string): string[] {
  return urls.filter((url) => new URL(url).origin !== origin)
}

// Hosts the style may name only as credit text (the map data's licence), never fetch from.
const CREDIT_ONLY = new Set(["https://openstreetmap.org"])

describe("the base map is held on this server", () => {
  afterEach(() => {
    document.documentElement.classList.remove("dark")
  })

  for (const dark of [false, true]) {
    it(`fetches nothing from an outside host (${dark ? "dark" : "light"} map)`, () => {
      if (dark) document.documentElement.classList.add("dark")
      const { result } = renderHook(() => useMapTheme())
      const origin = window.location.origin
      const fetched = offBox(allUrls(result.current), origin).filter((url) => !CREDIT_ONLY.has(new URL(url).origin))
      expect(fetched).toEqual([])
      const style = (result.current as { mapStyle?: unknown }).mapStyle
      expect(style, "the hook returns a style object, not an outside style address").toBeTypeOf("object")
      // tiles, fonts and symbols are all read from the page's own address
      const own = styleUrls(style)
      expect(own.length).toBeGreaterThanOrEqual(3)
      expect(offBox(own, origin)).toEqual([])
      expect(addProtocol).toHaveBeenCalledWith("pmtiles", expect.any(Function))
    })
  }

  it("builds every style address from the origin it is given", () => {
    const style = buildBasemapStyle(false, "http://104.196.62.215:5174")
    expect(style.glyphs).toBe("http://104.196.62.215:5174/basemap/assets/fonts/{fontstack}/{range}.pbf")
    expect(style.sprite).toBe("http://104.196.62.215:5174/basemap/assets/sprites/v4/grayscale")
    expect(offBox(styleUrls(style), "http://104.196.62.215:5174")).toEqual([])
    // the labels use only the fonts held on the server
    const fonts = new Set(
      style.layers.flatMap((layer) => {
        const font = (layer as { layout?: Record<string, unknown> }).layout?.["text-font"]
        return JSON.stringify(font ?? []).match(/Noto Sans[^"]*/g) ?? []
      }),
    )
    for (const font of fonts) {
      expect(["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic", "Noto Sans Devanagari Regular v1"]).toContain(font)
    }
  })

  it("every label a screen adds to a map names a font held on the server", () => {
    // a label with no text-font asks for maplibre's default font, which the server does not hold: a 404, then a rough local one
    const files: string[] = []
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = join(dir, entry.name)
        if (entry.isDirectory()) walk(path)
        else if (path.endsWith(".tsx") && !path.includes(".test.")) files.push(path)
      }
    }
    walk(join(process.cwd(), "src/features"))
    const labels = files.flatMap((file) =>
      readFileSync(file, "utf8").split('type="symbol"').slice(1).map((rest) => ({ file, layer: rest.split("/>")[0] })),
    )
    expect(labels.length).toBeGreaterThanOrEqual(3)
    const held = /"text-font": \["Noto Sans (Regular|Medium|Italic)"\]/
    expect(labels.filter(({ layer }) => !held.test(layer)).map(({ file }) => file)).toEqual([])
  })

  it("no map screen's source names an outside map host", () => {
    const roots = ["src/features/map", "src/features/graph", "src/features/phones"]
    const files: string[] = []
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name)
        if (statSync(path).isDirectory()) walk(path)
        else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) files.push(path)
      }
    }
    roots.forEach(walk)
    const mapHost = /https?:\/\/[^\s"'`]*(carto|mapbox|maptiler|arcgis|openstreetmap|tile|protomaps\.github|googleapis|stadiamaps|nominatim)/i
    // the map data's licence asks for a link to its copyright page in the credit line; that is text, not a fetch
    const hits = files.filter((file) =>
      mapHost.test(readFileSync(file, "utf8").replaceAll("https://openstreetmap.org/copyright", "")),
    )
    expect(hits).toEqual([])
  })

  it("says when the view is outside the area the held file covers", () => {
    const world: [number, number, number, number] = [-180, -85.0511, 180, 85.0511]
    expect(outsideCoverage(world, -77.03, 38.9)).toBe(false)
    expect(outsideCoverage(world, 540 - 77.03, 38.9)).toBe(false)
    const eastUs: [number, number, number, number] = [-90, 24, -66, 50]
    expect(outsideCoverage(eastUs, -77.03, 38.9)).toBe(false)
    expect(outsideCoverage(eastUs, 2.35, 48.85)).toBe(true)
    expect(outsideCoverage(null, 2.35, 48.85)).toBe(false)
  })
})
