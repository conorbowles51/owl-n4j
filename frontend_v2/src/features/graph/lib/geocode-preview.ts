export interface Coordinates {
  latitude: number
  longitude: number
}

export interface GeocodePreview extends Coordinates {
  query: string
  formattedAddress: string
}

const COORDINATE_EPSILON = 1e-9

function sameCoordinate(left: number, right: number) {
  return Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - right) <= COORDINATE_EPSILON
}

export function geocodePreviewMatchesCoordinates(
  preview: GeocodePreview | null,
  coordinates: Coordinates | null
): preview is GeocodePreview {
  if (!preview || !coordinates) return false
  return (
    sameCoordinate(preview.latitude, coordinates.latitude) &&
    sameCoordinate(preview.longitude, coordinates.longitude)
  )
}
