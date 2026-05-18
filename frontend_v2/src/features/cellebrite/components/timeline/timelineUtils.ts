import type { CellebriteRecord, PhoneReport, TimelineItem } from "../../types"
import { asText, isRecord, readText, reportTitle } from "../shared/cellebrite-format"
import { eventLabel, eventTimestamp, eventType, parseTs, reportKeyOf, toDateInput } from "../events/eventUtils"

type TimelineOperator = "type" | "from" | "to" | "app" | "phone" | "before" | "after" | "place" | "near"

type NearSpec = {
  lat: number
  lng: number
  radiusMeters: number
}

export type ParsedTimelineQuery = {
  raw: string
  terms: string[]
  excludes: string[]
  operators: {
    type: string[]
    from: string[]
    to: string[]
    app: string[]
    phone: string[]
    before: number | null
    after: number | null
    place: string[]
    near: NearSpec | null
  }
}

export type TimelineGroup = {
  day: string
  events: TimelineItem[]
}

const KNOWN_OPERATORS = new Set<TimelineOperator>([
  "type",
  "from",
  "to",
  "app",
  "phone",
  "before",
  "after",
  "place",
  "near",
])

const NO_MATCH = { matches: false, highlights: [] as string[] }

export function parseTimelineQuery(query: string): ParsedTimelineQuery {
  const parsed: ParsedTimelineQuery = {
    raw: query,
    terms: [],
    excludes: [],
    operators: {
      type: [],
      from: [],
      to: [],
      app: [],
      phone: [],
      before: null,
      after: null,
      place: [],
      near: null,
    },
  }

  if (!query.trim()) return parsed

  tokenise(query).forEach((token) => {
    let text = token
    let exclude = false
    if (text.startsWith("-") && text.length > 1) {
      exclude = true
      text = text.slice(1)
    }

    const opMatch = text.match(/^([a-zA-Z]+):(.*)$/)
    const op = opMatch?.[1]?.toLowerCase()
    const rawValue = stripQuotes(opMatch?.[2] ?? "").toLowerCase()
    const knownOp = op === "not" || (op ? KNOWN_OPERATORS.has(op as TimelineOperator) : false)

    if (opMatch && knownOp) {
      if (op === "not") {
        if (rawValue) parsed.excludes.push(rawValue)
        return
      }
      if (!rawValue) return
      if (op === "before" || op === "after") {
        const date = parseSearchDate(rawValue)
        if (date !== null) parsed.operators[op] = date
        return
      }
      if (op === "near") {
        parsed.operators.near = parseNear(rawValue)
        return
      }
      parsed.operators[op as Exclude<TimelineOperator, "before" | "after" | "near">].push(rawValue)
      return
    }

    const cleaned = stripQuotes(text).toLowerCase()
    if (!cleaned) return
    if (exclude) parsed.excludes.push(cleaned)
    else parsed.terms.push(cleaned)
  })

  return parsed
}

export function matchTimelineEvent(event: TimelineItem, parsed: ParsedTimelineQuery, reports: PhoneReport[]) {
  if (!parsed.raw.trim()) return { matches: true, highlights: [] as string[] }
  const { full, fields } = buildHaystack(event, reports)
  const { operators } = parsed

  if (operators.type.length && !valueMatches(operators.type, fields.type)) return NO_MATCH
  if (operators.from.length && !valueMatches(operators.from, fields.from)) return NO_MATCH
  if (operators.to.length && !valueMatches(operators.to, fields.to)) return NO_MATCH
  if (operators.app.length && !valueMatches(operators.app, fields.app)) return NO_MATCH
  if (operators.phone.length && !valueMatches(operators.phone, fields.phone)) return NO_MATCH
  if (operators.place.length && (!fields.place || !valueMatches(operators.place, fields.place))) return NO_MATCH

  if (operators.near) {
    const latitude = numberField(event, ["latitude", "lat"])
    const longitude = numberField(event, ["longitude", "lng", "lon"])
    if (latitude === null || longitude === null) return NO_MATCH
    if (haversineMeters(operators.near.lat, operators.near.lng, latitude, longitude) > operators.near.radiusMeters) {
      return NO_MATCH
    }
  }

  if (operators.before !== null || operators.after !== null) {
    const timestamp = parseTs(eventTimestamp(event))?.getTime() ?? null
    if (timestamp === null) return NO_MATCH
    if (operators.before !== null && timestamp > operators.before) return NO_MATCH
    if (operators.after !== null && timestamp < operators.after) return NO_MATCH
  }

  if (parsed.excludes.some((term) => full.includes(term))) return NO_MATCH

  const highlights: string[] = []
  for (const term of parsed.terms) {
    if (!full.includes(term)) return NO_MATCH
    highlights.push(term)
  }
  ;(["type", "from", "to", "app", "phone", "place"] as const).forEach((key) => {
    operators[key].forEach((term) => highlights.push(term))
  })

  return { matches: true, highlights: [...new Set(highlights.filter(Boolean))] }
}

export function groupTimelineEvents(events: TimelineItem[]): TimelineGroup[] {
  const sorted = [...events].sort((a, b) => {
    const aTime = parseTs(eventTimestamp(a))?.getTime() ?? 0
    const bTime = parseTs(eventTimestamp(b))?.getTime() ?? 0
    return bTime - aTime
  })
  const groups: TimelineGroup[] = []
  sorted.forEach((event) => {
    const day = toDateInput(parseTs(eventTimestamp(event)) ?? null) || "-"
    let group = groups[groups.length - 1]
    if (!group || group.day !== day) {
      group = { day, events: [] }
      groups.push(group)
    }
    group.events.push(event)
  })
  return groups
}

export function formatDayHeader(day: string): string {
  if (!day || day === "-") return "(no date)"
  const date = new Date(`${day}T00:00:00`)
  if (Number.isNaN(date.getTime())) return day
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function formatTimelineTime(event: TimelineItem): string {
  const date = parseTs(eventTimestamp(event))
  if (!date) return "-"
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

export function timelineDirection(event: TimelineItem): string {
  const sender = partyText(event.sender) || readText(event, ["sender_name", "from", "sender"])
  const recipients = partyList(event.recipients)
  const recipient = partyText(event.counterpart) || recipients[0] || readText(event, ["recipient_name", "to", "recipient"])
  if (sender && recipient) return `${sender} -> ${recipient}`
  if (sender) return sender
  if (recipient) return `-> ${recipient}`
  return ""
}

export function timelineSummary(event: TimelineItem): string {
  return readText(event, ["summary", "body", "label", "name", "description"], eventLabel(event))
}

export function splitForHighlight(text: string, highlights: string[]) {
  if (!text) return []
  const terms = highlights.map((term) => term.toLowerCase()).filter(Boolean).sort((a, b) => b.length - a.length)
  if (!terms.length) return [{ text, match: false }]

  const ranges: [number, number][] = []
  const lower = text.toLowerCase()
  terms.forEach((term) => {
    let from = 0
    while (from < lower.length) {
      const index = lower.indexOf(term, from)
      if (index < 0) break
      ranges.push([index, index + term.length])
      from = index + term.length
    }
  })

  if (!ranges.length) return [{ text, match: false }]
  ranges.sort((a, b) => a[0] - b[0])
  const merged: [number, number][] = []
  ranges.forEach((range) => {
    const last = merged[merged.length - 1]
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1])
    else merged.push([...range])
  })

  const parts: { text: string; match: boolean }[] = []
  let cursor = 0
  merged.forEach(([start, end]) => {
    if (start > cursor) parts.push({ text: text.slice(cursor, start), match: false })
    parts.push({ text: text.slice(start, end), match: true })
    cursor = end
  })
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false })
  return parts
}

function buildHaystack(event: TimelineItem, reports: PhoneReport[]) {
  const fields = {
    type: [eventType(event), readText(event, ["location_type", "subtype"])].filter(Boolean).join(" ").toLowerCase(),
    from: [partyText(event.sender), readText(event, ["sender_name", "from", "sender"])].filter(Boolean).join(" ").toLowerCase(),
    to: [
      partyText(event.counterpart),
      ...partyList(event.recipients),
      readText(event, ["recipient_name", "to", "recipient"]),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase(),
    app: readText(event, ["source_app", "app", "app_name"]).toLowerCase(),
    phone: phoneIdentity(event, reports).toLowerCase(),
    place: readText(event, ["location_formatted", "address", "place_name", "country", "country_code", "admin1", "admin2"]).toLowerCase(),
  }
  const full = [
    ...Object.values(fields),
    eventLabel(event),
    timelineSummary(event),
    readText(event, ["body", "direction", "deleted_state", "thread_id", "message_id", "node_key", "id"]),
    eventTimestamp(event),
    coordinateText(event),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
  return { full, fields }
}

function partyText(value: unknown): string {
  if (!value) return ""
  if (isRecord(value)) {
    return [readText(value, ["name", "display_name"]), readText(value, ["identifier", "phone", "key"])]
      .filter(Boolean)
      .join(" ")
  }
  return asText(value)
}

function partyList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(partyText).filter(Boolean)
}

function phoneIdentity(event: TimelineItem, reports: PhoneReport[]): string {
  const key = reportKeyOf(event)
  const report = reports.find((item) => item.report_key === key)
  if (!report) return key
  const short = Number.isInteger(report.display_index) ? `p${Number(report.display_index) + 1}` : ""
  return [short, reportTitle(report), report.device_model, report.phone_owner_name, report.owner_name, report.phone_number, report.imei]
    .filter(Boolean)
    .join(" ")
}

function coordinateText(event: TimelineItem): string {
  const latitude = numberField(event, ["latitude", "lat"])
  const longitude = numberField(event, ["longitude", "lng", "lon"])
  return latitude !== null && longitude !== null ? `${latitude} ${longitude}` : ""
}

function valueMatches(needles: string[], haystack: string): boolean {
  return needles.some((needle) => haystack.includes(needle))
}

function tokenise(input: string): string[] {
  const tokens: string[] = []
  let buffer = ""
  let inQuotes = false
  for (const char of input) {
    if (char === '"') {
      inQuotes = !inQuotes
      buffer += char
      continue
    }
    if (!inQuotes && /\s/.test(char)) {
      if (buffer) tokens.push(buffer)
      buffer = ""
      continue
    }
    buffer += char
  }
  if (buffer) tokens.push(buffer)
  return tokens
}

function stripQuotes(value: string): string {
  if (value.length >= 2 && value.startsWith('"') && value.endsWith('"')) return value.slice(1, -1)
  return value
}

function parseSearchDate(value: string): number | null {
  const cleaned = value.trim().replace(/\//g, "-")
  const date = new Date(cleaned.length === 10 ? `${cleaned}T00:00:00` : cleaned)
  return Number.isNaN(date.getTime()) ? null : date.getTime()
}

function parseNear(value: string): NearSpec | null {
  const [latRaw, lngRaw, radiusRaw] = value.split(",").map((part) => part.trim())
  const lat = Number.parseFloat(latRaw)
  const lng = Number.parseFloat(lngRaw)
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || !radiusRaw) return null
  const match = radiusRaw.toLowerCase().match(/^([\d.]+)\s*(km|m|meters|metres?)?$/)
  if (!match) return null
  const amount = Number.parseFloat(match[1])
  if (!Number.isFinite(amount) || amount <= 0) return null
  const unit = match[2] ?? "km"
  return { lat, lng, radiusMeters: unit === "m" || unit.startsWith("met") ? amount : amount * 1000 }
}

function numberField(row: CellebriteRecord, keys: string[]): number | null {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

function haversineMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const radius = 6371008.8
  const toRad = (degrees: number) => (degrees * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(a)))
}
