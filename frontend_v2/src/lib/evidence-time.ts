/**
 * How a phone time is written, everywhere (docs/cellebrite/03 section 3.2). The same rules as
 * backend/services/phone/time_display.py; both are tested against backend/tests/fixtures/time_cases.json so the
 * screen, copied text and the PDF agree byte for byte.
 *
 * Row "3:07 PM"; day header "Tuesday, March 14, 2023"; zone label "Eastern Time (UTC-4)", or
 * "Eastern Time (UTC-5 until 2:00 AM, then UTC-4)" on a day the offset changes; full form
 * "Tue, Mar 14, 2023, 3:07:12 PM EDT". Words are written here, never taken from the browser's locale, and zone
 * names come from the table below (D-30): a zone not listed is "<City> time" and its abbreviation is its offset.
 * Intl is used only to read the offset of a zone at an instant (numbers, not names).
 */

export const NO_TIME = "No time recorded"
export const NO_OFFSET_FLAG = "No offset in report"

/** Same as backend/services/phone/data/zone_names.json (a unit test asserts they are equal). */
export const ZONE_TABLE: Record<string, { name: string; std: string; dst: string; std_offset: number }> = {
  "America/New_York": { name: "Eastern Time", std: "EST", dst: "EDT", std_offset: -300 },
  "America/Detroit": { name: "Eastern Time", std: "EST", dst: "EDT", std_offset: -300 },
  "America/Chicago": { name: "Central Time", std: "CST", dst: "CDT", std_offset: -360 },
  "America/Denver": { name: "Mountain Time", std: "MST", dst: "MDT", std_offset: -420 },
  "America/Phoenix": { name: "Mountain Time", std: "MST", dst: "MDT", std_offset: -420 },
  "America/Los_Angeles": { name: "Pacific Time", std: "PST", dst: "PDT", std_offset: -480 },
  "America/Anchorage": { name: "Alaska Time", std: "AKST", dst: "AKDT", std_offset: -540 },
  "Pacific/Honolulu": { name: "Hawaii Time", std: "HST", dst: "HDT", std_offset: -600 },
  "America/Puerto_Rico": { name: "Atlantic Time", std: "AST", dst: "ADT", std_offset: -240 },
}

const UTC_NAMES = new Set(["UTC", "Etc/UTC", "Etc/GMT", "GMT", "Z"])
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

export function isUtc(zone: string): boolean {
  return UTC_NAMES.has(zone)
}

const formatters = new Map<string, Intl.DateTimeFormat>()
function partsFormatter(zone: string): Intl.DateTimeFormat {
  const key = isUtc(zone) ? "UTC" : zone
  let f = formatters.get(key)
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: key,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
    })
    formatters.set(key, f)
  }
  return f
}

export function validZone(zone: unknown): boolean {
  if (typeof zone !== "string" || !zone || zone.length > 64) return false
  try {
    partsFormatter(zone)
    return true
  } catch {
    return false
  }
}

interface Local {
  year: number
  month: number // 1-12
  day: number
  hour: number
  minute: number
  second: number
  weekday: number // 0 Sunday
}

function parseInstant(iso: string): number {
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(iso)) throw new Error("an instant must carry an offset")
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) throw new Error(`not an instant: ${iso}`)
  return ms
}

function localAt(ms: number, zone: string): Local {
  const parts = partsFormatter(zone).formatToParts(new Date(ms))
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? "0")
  const year = get("year")
  const month = get("month")
  const day = get("day")
  const hour = get("hour") % 24
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
  return { year, month, day, hour, minute: get("minute"), second: get("second"), weekday }
}

/** Minutes east of UTC for ``zone`` at the instant ``ms``. */
export function offsetMinutes(ms: number, zone: string): number {
  if (isUtc(zone)) return 0
  const l = localAt(Math.floor(ms / 1000) * 1000, zone)
  const asUtc = Date.UTC(l.year, l.month - 1, l.day, l.hour, l.minute, l.second)
  return Math.round((asUtc - Math.floor(ms / 1000) * 1000) / 60000)
}

export function offsetText(minutes: number): string {
  const sign = minutes >= 0 ? "+" : "-"
  const m = Math.abs(minutes)
  const h = Math.floor(m / 60)
  const r = m % 60
  return `UTC${sign}${h}${r ? `:${String(r).padStart(2, "0")}` : ""}`
}

export function zoneName(zone: string): string {
  if (isUtc(zone)) return "UTC"
  const entry = ZONE_TABLE[zone]
  if (entry) return entry.name
  const city = zone.split("/").pop() ?? zone
  return `${city.replace(/_/g, " ")} time`
}

export function abbreviation(ms: number, zone: string): string {
  if (isUtc(zone)) return "UTC"
  const off = offsetMinutes(ms, zone)
  const entry = ZONE_TABLE[zone]
  if (entry) return off === entry.std_offset ? entry.std : entry.dst
  return off === 0 ? "UTC" : offsetText(off)
}

function clock(h: number, m: number, s: number | null): string {
  const hh = h % 12 || 12
  return `${hh}:${String(m).padStart(2, "0")}${s === null ? "" : `:${String(s).padStart(2, "0")}`} ${h < 12 ? "AM" : "PM"}`
}

/** "3:07 PM" ("3:07:12 PM" with seconds); "No time recorded" when there is no instant. */
export function formatRowTime(iso: string | null | undefined, zone: string, seconds = false): string {
  if (!iso) return NO_TIME
  const l = localAt(parseInstant(iso), zone)
  return clock(l.hour, l.minute, seconds ? l.second : null)
}

/** "Tue, Mar 14, 2023, 3:07:12 PM EDT". */
export function formatFull(iso: string | null | undefined, zone: string): string {
  if (!iso) return NO_TIME
  const ms = parseInstant(iso)
  const l = localAt(ms, zone)
  return `${WEEKDAYS[l.weekday].slice(0, 3)}, ${MONTHS[l.month - 1].slice(0, 3)} ${l.day}, ${l.year}, ${clock(l.hour, l.minute, l.second)} ${abbreviation(ms, zone)}`
}

/** A time the report wrote without an offset: "Tue, Mar 14, 2023, 3:07:12 PM, no offset in report". */
export function formatWall(wall: string | null | undefined): string {
  if (!wall) return NO_TIME
  const m = wall.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return wall
  const [y, mo, d, h, mi, s] = [m[1], m[2], m[3], m[4], m[5], m[6] ?? "0"].map(Number)
  const wd = new Date(Date.UTC(y, mo - 1, d)).getUTCDay()
  return `${WEEKDAYS[wd].slice(0, 3)}, ${MONTHS[mo - 1].slice(0, 3)} ${d}, ${y}, ${clock(h, mi, s)}, no offset in report`
}

/** The calendar day ("2023-03-14") of an instant in ``zone``; null when there is no instant. */
export function dayOf(iso: string | null | undefined, zone: string): string | null {
  if (!iso) return null
  const l = localAt(parseInstant(iso), zone)
  return `${l.year}-${String(l.month).padStart(2, "0")}-${String(l.day).padStart(2, "0")}`
}

/** "Tuesday, March 14, 2023". */
export function formatDayHeader(day: string): string {
  const [y, m, d] = day.split("-").map(Number)
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
  return `${WEEKDAYS[wd]}, ${MONTHS[m - 1]} ${d}, ${y}`
}

/** The instant (ms) a calendar day starts in ``zone``. */
export function dayStart(day: string, zone: string): number {
  const [y, m, d] = day.split("-").map(Number)
  let guess = Date.UTC(y, m - 1, d)
  for (let i = 0; i < 3; i++) {
    guess = Date.UTC(y, m - 1, d) - offsetMinutes(guess, zone) * 60000
  }
  return guess
}

function nextDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number)
  const n = new Date(Date.UTC(y, m - 1, d + 1))
  return `${n.getUTCFullYear()}-${String(n.getUTCMonth() + 1).padStart(2, "0")}-${String(n.getUTCDate()).padStart(2, "0")}`
}

/** "UTC-4", or "UTC-5 until 2:00 AM, then UTC-4" on a day the offset changes (the wall clock before the change). */
export function dayOffsets(day: string, zone: string): string {
  const start = dayStart(day, zone)
  const last = dayStart(nextDay(day), zone) - 1000
  const a = offsetMinutes(start, zone)
  const b = offsetMinutes(last, zone)
  if (a === b) return offsetText(a)
  let lo = start
  let hi = last
  while (hi - lo > 1000) {
    const mid = lo + Math.floor((hi - lo) / 2000) * 1000
    if (offsetMinutes(mid, zone) === a) lo = mid
    else hi = mid
  }
  const before = new Date(hi + a * 60000)
  return `${offsetText(a)} until ${clock(before.getUTCHours(), before.getUTCMinutes(), null)}, then ${offsetText(b)}`
}

/** "Eastern Time (UTC-4)"; "UTC" for UTC. */
export function zoneLabel(day: string, zone: string): string {
  if (isUtc(zone)) return "UTC"
  return `${zoneName(zone)} (${dayOffsets(day, zone)})`
}

/** Converts a date picked in ``zone`` to the instants of that day's start and end (03 section 4.3). */
export function dayRange(day: string, zone: string): { from: string; to: string } {
  return { from: new Date(dayStart(day, zone)).toISOString(), to: new Date(dayStart(nextDay(day), zone) - 1).toISOString() }
}
