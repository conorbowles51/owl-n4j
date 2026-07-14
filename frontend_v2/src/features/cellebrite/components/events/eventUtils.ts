import {
  Calendar,
  Globe,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Radio,
  Search,
  Smartphone,
  Unlock,
  Users,
  Wifi,
  Zap,
} from "lucide-react"

import type { CellebriteRecord, EventTrack, PhoneReport, TimelineItem, TrackPoint } from "../../types"
import { asText, readNumber, readText, reportTitle } from "../shared/cellebrite-format"

export const EVENT_COLORS: Record<string, string> = {
  location: "#06b6d4",
  cell_tower: "#8b5cf6",
  wifi: "#10b981",
  call: "#2563eb",
  message: "#0c9da0",
  email: "#ef4444",
  power: "#6b7280",
  device_event: "#64748b",
  app_session: "#14b8a6",
  search: "#db2777",
  visit: "#9333ea",
  meeting: "#f97316",
}

export const EVENT_LABELS: Record<string, string> = {
  location: "Location",
  cell_tower: "Cell tower",
  wifi: "WiFi",
  call: "Call",
  message: "Message",
  email: "Email",
  power: "Power",
  device_event: "Device event",
  app_session: "App",
  search: "Search",
  visit: "Visit",
  meeting: "Meeting",
}

export const EVENT_ICONS = {
  location: MapPin,
  cell_tower: Radio,
  wifi: Wifi,
  call: Phone,
  message: MessageSquare,
  email: Mail,
  power: Zap,
  device_event: Unlock,
  app_session: Smartphone,
  search: Search,
  visit: Globe,
  meeting: Users,
  calendar: Calendar,
}

export const PLAYBACK_SPEEDS = [1, 2, 5, 10, 30, 60, 300, 1800]

export type EventsViewMode = "map" | "split" | "table"

export function eventKey(event: TimelineItem | CellebriteRecord, fallback = "event"): string {
  return readText(event, ["id", "node_key", "key"], fallback)
}

export function eventType(event: TimelineItem | CellebriteRecord): string {
  return readText(event, ["event_type", "type"], "event")
}

export function eventLabel(event: TimelineItem | CellebriteRecord): string {
  return readText(event, ["label", "summary", "body", "name", "event_type", "type"], "Event")
}

export function eventColor(type: string): string {
  return EVENT_COLORS[type] ?? "#64748b"
}

export function eventTypeLabel(row: CellebriteRecord): string {
  const type = readText(row, ["event_type", "type"], "event")
  return readText(row, ["label"], EVENT_LABELS[type] ?? type)
}

export function eventTimestamp(event: TimelineItem | CellebriteRecord): string {
  return readText(event, ["timestamp", "datetime", "time", "date"])
}

export function parseTs(value: unknown): Date | null {
  const text = asText(value)
  if (!text) return null
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatTs(value: unknown): string {
  const date = value instanceof Date ? value : parseTs(value)
  if (!date) return asText(value)
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

export function toDateInput(value: Date | string | null): string {
  if (!value) return ""
  const date = value instanceof Date ? value : parseTs(value)
  if (!date) return ""
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function locationOf(row: TimelineItem | TrackPoint | CellebriteRecord): { longitude: number; latitude: number } | null {
  const latitude = readNumber(row, ["latitude", "lat"], Number.NaN)
  const longitude = readNumber(row, ["longitude", "lng", "lon"], Number.NaN)
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
  return { latitude, longitude }
}

export function reportKeyOf(row: CellebriteRecord): string {
  return readText(row, ["device_report_key", "report_key", "cellebrite_report_key"])
}

export function reportMaps(reports: PhoneReport[]) {
  const labelByKey = new Map<string, string>()
  const colorByKey = new Map<string, string>()
  const palette = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#0891b2", "#f97316", "#db2777"]
  reports.forEach((report, index) => {
    labelByKey.set(report.report_key, reportTitle(report))
    colorByKey.set(report.report_key, palette[index % palette.length])
  })
  return { labelByKey, colorByKey }
}

export function reportLabel(row: CellebriteRecord, labels: Map<string, string>): string {
  const key = reportKeyOf(row)
  return labels.get(key) ?? key
}

export function dateRangeFromEvents(events: TimelineItem[]): { min: Date | null; max: Date | null } {
  let min: Date | null = null
  let max: Date | null = null
  events.forEach((event) => {
    const date = parseTs(eventTimestamp(event))
    if (!date) return
    if (!min || date < min) min = date
    if (!max || date > max) max = date
  })
  return { min, max }
}

export function eventsWithinTrail(events: TimelineItem[], playheadTime: Date | null, trailWindowMs: number): TimelineItem[] {
  if (!playheadTime) return events
  const end = playheadTime.getTime()
  const start = end - trailWindowMs
  return events.filter((event) => {
    const date = parseTs(eventTimestamp(event))
    if (!date) return false
    const ms = date.getTime()
    return ms >= start && ms <= end
  })
}

export function eventMatchesSearch(event: TimelineItem, query: string, reportLabels: Map<string, string>): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    eventLabel(event),
    eventType(event),
    readText(event, ["source_app", "app"]),
    readText(event, ["sender_name", "from", "sender"]),
    readText(event, ["recipient_name", "to", "recipient"]),
    readText(event, ["summary", "body"]),
    reportLabel(event, reportLabels),
  ]
    .join(" ")
    .toLowerCase()
    .includes(needle)
}

export function trackPoints(track: EventTrack): { longitude: number; latitude: number; timestamp?: string | null }[] {
  const rows = track.points ?? track.coordinates ?? []
  const points: { longitude: number; latitude: number; timestamp?: string | null }[] = []
  rows.forEach((point) => {
    const location = locationOf(point)
    if (location) points.push({ ...location, timestamp: point.timestamp })
  })
  return points
}

export function trackReportKey(track: EventTrack): string {
  return readText(track, ["device_report_key", "report_key", "cellebrite_report_key"])
}

export function clampPlayhead(playhead: Date | null, events: TimelineItem[]): Date | null {
  const range = dateRangeFromEvents(events)
  if (!range.min || !range.max) return null
  if (!playhead) return range.min
  if (playhead < range.min) return range.min
  if (playhead > range.max) return range.max
  return playhead
}
