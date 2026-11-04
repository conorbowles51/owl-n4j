import { ApiError } from "@/lib/api-client"
import type { DecisionNote } from "../api"

const LIST_ZONES = ["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Mexico_City", "Europe/London", "Europe/Dublin"]

/** Time zone names this browser knows; the short list where it cannot say. */
export function ZONES(): string[] {
  return typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : LIST_ZONES
}

/** The server's own sentence for a refused save (a 4xx detail), else the fallback. */
export function setupError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const d = (error.data as { detail?: unknown } | undefined)?.detail
    if (typeof d === "string") return d
  }
  return fallback
}

export function decidedWords(d: DecisionNote): string {
  const day = d.at ? d.at.slice(0, 10) : null
  return `Set${d.by ? ` by ${d.by}` : ""}${day ? ` on ${day}` : ""}${d.reason ? `: ${d.reason}` : ""}.`
}

function amount(seconds: number): string {
  const n = Math.abs(seconds)
  const parts: [string, number][] = [["day", Math.floor(n / 86400)], ["hour", Math.floor((n % 86400) / 3600)], ["minute", Math.floor((n % 3600) / 60)], ["second", n % 60]]
  return parts.filter(([, v]) => v).map(([w, v]) => `${v} ${w}${v === 1 ? "" : "s"}`).join(", ")
}

/** The stored offset is added to the phone's time: a negative one means the clock ran fast. */
export const offsetAmountWords = (seconds: number) => `Clock ran ${seconds < 0 ? "fast" : "slow"} by ${amount(seconds)}`

export function clockPeriodWords(start: string | null, end: string | null): string {
  if (!start && !end) return "for the whole phone"
  if (!end) return `from ${start!.slice(0, 10)}`
  if (!start) return `before ${end.slice(0, 10)}`
  return `from ${start.slice(0, 10)} to before ${end.slice(0, 10)}`
}

/** What the form asks for, or null while it does not yet name an amount. A fast clock is moved back. `to` is
 * inclusive on screen, so the period ends at the start of the next UTC day. */
export function clockRequest(way: "fast" | "slow", minutes: string, seconds: string, from: string, to: string) {
  const total = (Number(minutes) || 0) * 60 + (Number(seconds) || 0)
  if (!Number.isInteger(total) || total <= 0) return null
  const next = to ? new Date(Date.parse(`${to}T00:00:00Z`) + 86_400_000).toISOString().replace(".000Z", "Z") : null
  return { seconds: way === "fast" ? -total : total, start: from ? `${from}T00:00:00Z` : null, end: next }
}
