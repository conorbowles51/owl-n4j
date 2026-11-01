/**
 * Day plus 12-hour time with the zone named in words (07 4.11, lesson table: "only shows time, not the day ...
 * military time"). Used by the kit and the prototype until the one Timeline formatter (lib/evidence-time.ts,
 * unit 03-6) exists; then this module re-exports it and the kit tests keep the wording.
 */

const ZONE_NAMES: Record<string, string> = {
  "America/New_York": "Eastern time",
  "America/Chicago": "Central time",
  "America/Denver": "Mountain time",
  "America/Los_Angeles": "Pacific time",
  UTC: "UTC",
  "Etc/UTC": "UTC",
  "Europe/London": "UK time",
}

export function offsetWords(iso: string, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "longOffset" }).formatToParts(new Date(iso))
  const raw = parts.find((p) => p.type === "timeZoneName")?.value ?? "GMT"
  const m = raw.match(/GMT([+-]\d{2}):?(\d{2})?/)
  if (!m) return "UTC"
  const hours = Number(m[1])
  const mins = m[2] && m[2] !== "00" ? `:${m[2]}` : ""
  return `UTC${hours >= 0 ? "+" : "-"}${Math.abs(hours)}${mins}`
}

export function zoneWords(iso: string, zone: string): string {
  const name = ZONE_NAMES[zone] ?? zone.replace(/_/g, " ")
  const off = offsetWords(iso, zone)
  return name === "UTC" ? "UTC" : `${name} (${off})`
}

/** "Tuesday 5 March 2024, 3:04 PM, Eastern time (UTC-5)"; seconds when asked (rows sharing a minute). */
export function instantWords(iso: string, zone: string, withSeconds = false): string {
  const d = new Date(iso)
  const day = new Intl.DateTimeFormat("en-GB", { timeZone: zone, weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(d).replace(",", "")
  const time = new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "numeric", minute: "2-digit", second: withSeconds ? "2-digit" : undefined, hour12: true }).format(d)
  return `${day}, ${time}, ${zoneWords(iso, zone)}`
}

/** The row's short time: "3:04 PM" (12-hour), seconds when two rows share a minute. */
export function timeOfDay(iso: string, zone: string, withSeconds = false): string {
  return new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "numeric", minute: "2-digit", second: withSeconds ? "2-digit" : undefined, hour12: true }).format(new Date(iso))
}
