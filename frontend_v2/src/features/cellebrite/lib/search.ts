import type { CellebriteRecord, PhoneReport } from "../types"

type TextOperator = "type" | "from" | "to" | "app" | "phone" | "place"

const KNOWN_OPERATORS = new Set<string>([
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

const TEXT_OPERATORS = new Set<string>(["type", "from", "to", "app", "phone", "place"])

export interface NearSpec {
  lat: number
  lng: number
  radiusMeters: number
}

export interface ParsedCellebriteQuery {
  raw: string
  terms: string[]
  excludes: string[]
  operators: {
    type: string | string[] | null
    from: string | string[] | null
    to: string | string[] | null
    app: string | string[] | null
    phone: string | string[] | null
    before: number | null
    after: number | null
    place: string | string[] | null
    near: NearSpec | null
  }
}

const EMPTY_OPERATORS: ParsedCellebriteQuery["operators"] = {
  type: null,
  from: null,
  to: null,
  app: null,
  phone: null,
  before: null,
  after: null,
  place: null,
  near: null,
}

export function parseCellebriteQuery(query: string): ParsedCellebriteQuery {
  const parsed: ParsedCellebriteQuery = {
    raw: query || "",
    terms: [],
    excludes: [],
    operators: { ...EMPTY_OPERATORS },
  }
  if (!query.trim()) return parsed

  for (const originalToken of tokenise(query)) {
    let token = originalToken
    let exclude = false
    if (token.startsWith("-") && token.length > 1) {
      exclude = true
      token = token.slice(1)
    }

    const operatorMatch = token.match(/^([a-zA-Z]+):(.*)$/)
    const operatorName = operatorMatch?.[1]?.toLowerCase()
    const knownOperator =
      operatorName === "not" || (operatorName ? KNOWN_OPERATORS.has(operatorName) : false)

    if (operatorMatch && operatorName && knownOperator) {
      const value = stripQuotes(operatorMatch[2]).toLowerCase()
      if (!value) continue
      if (operatorName === "not") {
        parsed.excludes.push(value)
        continue
      }
      if (operatorName === "before" || operatorName === "after") {
        const dateValue = parseDate(value)
        if (dateValue != null) parsed.operators[operatorName] = dateValue
        continue
      }
      if (operatorName === "near") {
        const near = parseNearSpec(value)
        if (near) parsed.operators.near = near
        continue
      }
      if (isTextOperator(operatorName)) addOperatorValue(parsed, operatorName, value)
      continue
    }

    const cleaned = stripQuotes(token).toLowerCase()
    if (!cleaned) continue
    if (exclude) parsed.excludes.push(cleaned)
    else parsed.terms.push(cleaned)
  }

  return parsed
}

function isTextOperator(value: string): value is TextOperator {
  return TEXT_OPERATORS.has(value)
}

function addOperatorValue(parsed: ParsedCellebriteQuery, key: TextOperator, value: string) {
  const current = parsed.operators[key]
  if (typeof current === "number" || (current && typeof current === "object")) return
  if (current == null) {
    parsed.operators[key] = value
  } else if (Array.isArray(current)) {
    current.push(value)
  } else {
    parsed.operators[key] = [current, value]
  }
}

function tokenise(input: string) {
  const tokens: string[] = []
  let buffer = ""
  let inQuotes = false
  for (const char of input) {
    if (char === "\"") {
      inQuotes = !inQuotes
      buffer += char
      continue
    }
    if (!inQuotes && /\s/.test(char)) {
      if (buffer) {
        tokens.push(buffer)
        buffer = ""
      }
      continue
    }
    buffer += char
  }
  if (buffer) tokens.push(buffer)
  return tokens
}

function stripQuotes(value: string) {
  if (value.length >= 2 && value.startsWith("\"") && value.endsWith("\"")) {
    return value.slice(1, -1)
  }
  return value
}

function parseDate(value: string) {
  const cleaned = value.trim().replace(/\//g, "-")
  const date = new Date(cleaned.length === 10 ? `${cleaned}T00:00:00` : cleaned)
  return Number.isNaN(date.getTime()) ? null : date.getTime()
}

function parseNearSpec(raw: string): NearSpec | null {
  const parts = raw.split(",").map((part) => part.trim())
  if (parts.length < 3) return null
  const lat = Number.parseFloat(parts[0])
  const lng = Number.parseFloat(parts[1])
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null
  const radiusMatch = parts[2].toLowerCase().match(/^([\d.]+)\s*(km|m|meters|metre|meter)?$/)
  if (!radiusMatch) return null
  const radius = Number.parseFloat(radiusMatch[1])
  if (!Number.isFinite(radius) || radius <= 0) return null
  const unit = radiusMatch[2] || "km"
  return {
    lat,
    lng,
    radiusMeters: unit === "m" || unit.startsWith("met") ? radius : radius * 1000,
  }
}

function textValue(value: unknown) {
  if (value == null) return ""
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return ""
}

function partyText(value: unknown) {
  if (!value || typeof value !== "object") return ""
  const party = value as CellebriteRecord
  return [
    party.name,
    party.identifier,
    party.phone,
    party.key,
  ].map(textValue).filter(Boolean).join(" ")
}

function arrayPartyText(value: unknown) {
  if (!Array.isArray(value)) return ""
  return value.map(partyText).filter(Boolean).join(" ")
}

function reportPhoneText(reportKey: string, reports: PhoneReport[]) {
  const report = reports.find((candidate) => candidate.report_key === reportKey)
  if (!report) return ""
  const label =
    typeof report.display_index === "number" && report.display_index >= 0
      ? `p${report.display_index + 1}`
      : ""
  return [
    label,
    report.device_name_override,
    report.device_name,
    report.device_model,
    report.phone_owner_name,
    report.phone_number,
  ].map(textValue).filter(Boolean).join(" ")
}

export function buildCellebriteHaystack(
  item: CellebriteRecord,
  kind: "thread" | "item" | "event",
  reports: PhoneReport[] = []
) {
  const fields = {
    type: "",
    from: "",
    to: "",
    app: "",
    phone: "",
    place: "",
  }

  const reportKey = textValue(item.device_report_key || item.report_key)
  fields.phone = reportKey ? reportPhoneText(reportKey, reports).toLowerCase() : ""

  if (kind === "thread") {
    fields.type = textValue(item.thread_type).toLowerCase()
    fields.app = textValue(item.source_app).toLowerCase()
    const participants = arrayPartyText(item.participants).toLowerCase()
    fields.from = participants
    fields.to = participants
  } else {
    fields.type = textValue(item.event_type || item.type || item.thread_type).toLowerCase()
    fields.app = textValue(item.source_app || item.app_name).toLowerCase()
    fields.from = partyText(item.sender).toLowerCase()
    fields.to = [
      arrayPartyText(item.recipients),
      partyText(item.counterpart),
    ].filter(Boolean).join(" ").toLowerCase()
  }

  fields.place = [
    item.address,
    item.place_name,
    item.country,
    item.country_code,
    item.admin1,
    item.admin2,
    item.location_formatted,
  ].map(textValue).filter(Boolean).join(" ").toLowerCase()

  const full = [
    fields.type,
    fields.from,
    fields.to,
    fields.app,
    fields.phone,
    fields.place,
    item.name,
    item.label,
    item.summary,
    item.body,
    item.subject,
    item.direction,
    item.thread_id,
    item.key,
  ].map(textValue).filter(Boolean).join(" ").toLowerCase()

  return { full, fields }
}

function timestampOf(item: CellebriteRecord, kind: "thread" | "item" | "event") {
  const raw =
    kind === "thread"
      ? item.last_activity || item.last_message_at || item.timestamp
      : item.timestamp || item.date
  const value = textValue(raw)
  if (!value) return null
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? null : time
}

function operatorMatches(needle: string | string[] | null, haystack: string) {
  if (!needle) return true
  if (Array.isArray(needle)) return needle.some((item) => haystack.includes(item))
  return haystack.includes(needle)
}

function coordinate(value: unknown) {
  const numeric = typeof value === "number" ? value : Number.parseFloat(textValue(value))
  return Number.isFinite(numeric) ? numeric : null
}

function haversineMeters(lat1: number, lng1: number, lat2: number, lng2: number) {
  const earthRadiusMeters = 6371008.8
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180
  const deltaLat = toRadians(lat2 - lat1)
  const deltaLng = toRadians(lng2 - lng1)
  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) *
      Math.cos(toRadians(lat2)) *
      Math.sin(deltaLng / 2) ** 2
  return 2 * earthRadiusMeters * Math.asin(Math.min(1, Math.sqrt(a)))
}

export function matchCellebriteItem(
  item: CellebriteRecord,
  parsed: ParsedCellebriteQuery,
  kind: "thread" | "item" | "event",
  reports: PhoneReport[] = []
) {
  const { full, fields } = buildCellebriteHaystack(item, kind, reports)
  const ops = parsed.operators
  if (!operatorMatches(ops.type, fields.type)) return { matches: false, highlights: [] }
  if (!operatorMatches(ops.from, fields.from)) return { matches: false, highlights: [] }
  if (!operatorMatches(ops.to, fields.to)) return { matches: false, highlights: [] }
  if (!operatorMatches(ops.app, fields.app)) return { matches: false, highlights: [] }
  if (!operatorMatches(ops.phone, fields.phone)) return { matches: false, highlights: [] }
  if (ops.place && (!fields.place || !operatorMatches(ops.place, fields.place))) {
    return { matches: false, highlights: [] }
  }
  if (ops.near) {
    const lat = coordinate(item.latitude || item.lat)
    const lng = coordinate(item.longitude || item.lng)
    if (lat == null || lng == null) return { matches: false, highlights: [] }
    if (haversineMeters(ops.near.lat, ops.near.lng, lat, lng) > ops.near.radiusMeters) {
      return { matches: false, highlights: [] }
    }
  }
  if (ops.before != null || ops.after != null) {
    const timestamp = timestampOf(item, kind)
    if (timestamp == null) return { matches: false, highlights: [] }
    if (ops.before != null && timestamp > ops.before) return { matches: false, highlights: [] }
    if (ops.after != null && timestamp < ops.after) return { matches: false, highlights: [] }
  }
  if (parsed.excludes.some((term) => full.includes(term))) {
    return { matches: false, highlights: [] }
  }
  for (const term of parsed.terms) {
    if (!full.includes(term)) return { matches: false, highlights: [] }
  }
  return { matches: true, highlights: collectHighlights(parsed) }
}

function collectHighlights(parsed: ParsedCellebriteQuery) {
  const highlights = [...parsed.terms]
  for (const key of ["type", "from", "to", "app", "phone", "place"] as const) {
    const value = parsed.operators[key]
    if (Array.isArray(value)) highlights.push(...value)
    else if (value) highlights.push(value)
  }
  return Array.from(new Set(highlights))
}

export function splitForHighlight(text: string | null | undefined, highlights: string[]) {
  if (!text) return []
  const sorted = highlights.filter(Boolean).sort((a, b) => b.length - a.length)
  if (!sorted.length) return [{ text, match: false }]
  const lower = text.toLowerCase()
  const ranges: [number, number][] = []
  for (const term of sorted) {
    let index = lower.indexOf(term.toLowerCase())
    while (index >= 0) {
      ranges.push([index, index + term.length])
      index = lower.indexOf(term.toLowerCase(), index + term.length)
    }
  }
  if (!ranges.length) return [{ text, match: false }]
  ranges.sort((left, right) => left[0] - right[0])
  const merged: [number, number][] = []
  for (const range of ranges) {
    const last = merged[merged.length - 1]
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1])
    else merged.push([...range])
  }
  const segments: { text: string; match: boolean }[] = []
  let cursor = 0
  for (const [start, end] of merged) {
    if (start > cursor) segments.push({ text: text.slice(cursor, start), match: false })
    segments.push({ text: text.slice(start, end), match: true })
    cursor = end
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), match: false })
  return segments
}

export function extractParticipantKeys(row: CellebriteRecord) {
  const candidates = [
    row.participant_keys,
    row.entity_keys,
    row.person_keys,
    row.contact_keys,
    row.keys,
    row.key ? [row.key] : null,
  ]
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate.map(textValue).filter(Boolean)
    }
  }
  return []
}
