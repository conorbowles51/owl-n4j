import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * maplibre-gl 6 moved the camera off the map object: `map.transform` is gone. react-map-gl below 8.1.3 still reads
 * it on every camera event, so each move threw "Cannot read properties of undefined (reading 'center')" (live
 * 9 Nov 2026: 54 page errors moving map -> timeline -> map) and the map's onMove/onMoveEnd handlers never ran.
 * 8.1.3 reads the camera through `getTransformLike` and `setTransformCameraUpdate`.
 */
describe("map library versions", () => {
  const lock = JSON.parse(readFileSync(resolve(__dirname, "../../../package-lock.json"), "utf8")) as {
    packages: Record<string, { version: string }>
  }
  const version = (name: string) => lock.packages[`node_modules/${name}`].version.split(".").map(Number)

  it("pairs maplibre-gl 6 with a react-maplibre that reads the camera the v6 way", () => {
    const [major] = version("maplibre-gl")
    if (major < 6) return
    const [a, b, c] = version("@vis.gl/react-maplibre")
    expect(a * 1_000_000 + b * 1_000 + c).toBeGreaterThanOrEqual(8_001_003)
  })
})
