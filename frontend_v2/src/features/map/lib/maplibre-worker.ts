import * as maplibregl from "maplibre-gl"
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url"

/**
 * maplibre-gl 6 runs its tile worker from a separate module file that its main bundle locates by
 * import.meta.url. Bundled into /assets/ that file is not emitted (404, the map stays black), so the
 * file is named to the bundler here and its built URL handed to maplibre before any map is created.
 * Import this module (for its effect) in every file that creates a map.
 */
maplibregl.setWorkerUrl(workerUrl)
