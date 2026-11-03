/** Metres per pixel at zoom 20 on the equator for 512-pixel tiles (MapLibre): 40,075,016.686 m / 512 / 2^20. */
export const METRES_PER_PIXEL_Z20 = 40075016.686 / 512 / 2 ** 20

/** A radius in metres as pixels at zoom 20 at this latitude, so the circle shows the accuracy the phone reported. */
export function accuracyPixelsAtZoom20(metres: number, lat: number): number {
  return metres / (METRES_PER_PIXEL_Z20 * Math.max(0.01, Math.cos((lat * Math.PI) / 180)))
}
