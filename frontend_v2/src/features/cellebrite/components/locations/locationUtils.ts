import type { CellebriteRecord, LocationTile, PhoneReport, TimelineItem } from "../../types"
import { readList, readNumber, readText } from "../shared/cellebrite-format"
import { eventKey, eventLabel, locationOf, reportLabel } from "../events/eventUtils"

export type LocationRenderMode = "tiles" | "raw"

export function tileToLocationEvent(tile: LocationTile, cellDeg: number): TimelineItem {
  const key = readText(tile, ["tile_id"], `tile-${readNumber(tile, ["cell_y"])}-${readNumber(tile, ["cell_x"])}`)
  const count = readNumber(tile, ["count"], 0)
  const apps = readList(tile, ["top_apps"])
  return {
    ...tile,
    id: key,
    node_key: key,
    key,
    event_type: "location_tile",
    type: "location_tile",
    label: `${count.toLocaleString()} location${count === 1 ? "" : "s"}`,
    summary: apps.length ? `Apps: ${apps.join(", ")}` : "",
    latitude: readNumber(tile, ["lat", "latitude"], Number.NaN),
    longitude: readNumber(tile, ["lon", "lng", "longitude"], Number.NaN),
    is_geolocated: true,
    location_source: "direct",
    cell_deg: cellDeg,
  }
}

export function locationSearchText(row: TimelineItem | CellebriteRecord, reports: PhoneReport[]): string {
  const labels = new Map(reports.map((report) => [report.report_key, report.device_name_override || report.device_name || report.report_key]))
  const loc = locationOf(row)
  return [
    eventLabel(row),
    readText(row, ["location_type", "source_app", "app", "address", "place_name", "country", "admin1", "admin2"]),
    readList(row, ["top_apps"]).join(" "),
    reportLabel(row, labels),
    loc ? `${loc.latitude},${loc.longitude}` : "",
  ].join(" ")
}

export function locationId(row: TimelineItem | CellebriteRecord, fallback = "location"): string {
  return eventKey(row, fallback)
}

export function locationTitle(row: TimelineItem | CellebriteRecord): string {
  return readText(row, ["label", "location_type", "address", "place_name"], "Location")
}

export function locationCoordinateLabel(row: TimelineItem | CellebriteRecord): string {
  const loc = locationOf(row)
  if (!loc) return "-"
  return `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`
}

export function tileCellDeg(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 0
}
