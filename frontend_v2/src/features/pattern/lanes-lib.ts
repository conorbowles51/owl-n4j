import { ApiError } from "@/lib/api-client"
import { phoneLinkHref } from "@/features/phones/phone-links"
import type { DayResponse, KeyDate, LaneItem, Snapshot } from "./api"
import type { LaneBand, LaneRow } from "./components/Lanes"

/** Helpers shared by the Patterns screen, the window panel and the statement check (kept apart from components). */
export function errorWords(e: unknown) {
  if (e instanceof ApiError) {
    const d = (e.data as { detail?: unknown } | undefined)?.detail
    if (typeof d === "string") return d
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message)
    return e.message
  }
  return e instanceof Error ? e.message : String(e)
}

/** Hour states of one phone as bands, merged where neighbours share a state. */
export function bandsFromHours(hours: { hour_utc: string; state: string; words: string; has_records?: boolean }[]): LaneBand[] {
  const out: LaneBand[] = []
  for (const h of hours) {
    const end = new Date(new Date(h.hour_utc).getTime() + 3600_000).toISOString()
    const last = out[out.length - 1]
    const hasRecords = !!h.has_records
    // one band per state, words and records: a not-observed hour holding records reads and shades apart from "No data"
    if (last && last.state === h.state && last.words === h.words && !!last.hasRecords === hasRecords
      && last.end === new Date(h.hour_utc).toISOString()) last.end = end
    else out.push({ start: new Date(h.hour_utc).toISOString(), end, state: h.state, words: h.words, ...(hasRecords ? { hasRecords } : {}) })
  }
  return out
}

function itemLabel(i: LaneItem) {
  if (i.ref_kind === "comm_event") {
    const who = (i.parties || []).map((p) => p.name || p.identifier).filter(Boolean).join(", ")
    return `${i.kind} ${i.direction}${who ? ` · ${who}` : ""}`
  }
  if (i.ref_kind === "place_observation") return `${i.source_kind} · ${i.radius_m ? `${Math.round(i.radius_m)} m` : "Accuracy not recorded"}`
  return `${i.record_type} · ${i.field} (${i.meaning})`
}

export function laneRowsOf(caseId: string, d: DayResponse | (DayResponse & { label?: string })): LaneRow[] {
  const href = (i: LaneItem) => i.record_uid ? phoneLinkHref(caseId, { target_type: "phone_record", target_id: i.record_uid }) : null
  const rows: LaneRow[] = d.availability.map((a) => ({ id: `avail-${a.extraction_id}`, label: a.phone || "Phone", bands: bandsFromHours(a.hours), marks: [], total: 0, note: "recording" }))
  for (const k of ["interaction", "device_state", "communications", "places", "others", "passive"]) {
    const items = d.lanes[k] || []
    rows.push({
      id: k, label: d.lane_words[k] || k, total: d.totals[k] ?? items.length, collapsible: k === "device_state" || k === "passive",
      hiddenAs: k === "passive" ? ["record made without use", "records made without use"] as [string, string] : undefined,
      note: k === "passive" && d.passive_as_hourly_counts ? d.limit_words || undefined : undefined,
      marks: items.map((i) => ({ key: `${i.ref_kind}:${i.id}`, at: i.at, end: i.end, label: itemLabel(i),
        detail: [i.strength && `strength ${i.strength}`, i.actor && `actor ${i.actor}`, i.source_app, i.phone, ...(i.flags || []).map((f) => d.flag_words?.[f] || f)].filter(Boolean).join(" · "),
        tone: (i.strength as never) || "none", href: href(i) })),
    })
  }
  const money = (d.lanes.money || []) as unknown as { transaction_id: string; amount_minor: number; currency: string; date_words: string; counterparty: string | null }[]
  rows.push({ id: "money", label: d.lane_words.money || "Payments", total: d.totals.money ?? money.length, marks: [],
    allDay: money.map((m) => ({ key: m.transaction_id, label: `${(m.amount_minor / 100).toFixed(2)} ${m.currency}${m.counterparty ? ` · ${m.counterparty}` : ""}`, detail: m.date_words })) })
  return rows
}

export function keyDateWords(k: KeyDate) {
  return k.local ? `${k.label} · ${k.local.slice(0, 16).replace("T", " ")} (${k.zone})` : k.label
}

function wallOf(t: number, zone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(new Date(t))
  const get = (x: string) => Number(parts.find((p) => p.type === x)?.value)
  return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"))
}

/**
 * A wall-clock time typed for a zone, as an instant. The offset is read at the candidate moment and read again at
 * the result, so a time near a clock change lands on the right side of it. A time the clock skipped (spring
 * forward) is refused ("missing"); a time the clock shows twice (fall back) is the earlier of the two (04 decision 34).
 */
export function zonedResult(local: string, zone: string): { instant: string | null; problem: "zone" | "missing" | null } {
  if (!local) return { instant: null, problem: null }
  const wall = new Date(`${local}:00Z`).getTime()
  if (Number.isNaN(wall)) return { instant: null, problem: "zone" }
  try {
    const candidates = new Set<number>()
    for (const probe of [wall - 86_400_000, wall, wall + 86_400_000]) {
      const offset = wallOf(probe, zone) - probe
      const t = wall - offset
      if (wallOf(t, zone) === wall) candidates.add(t)
    }
    if (candidates.size === 0) return { instant: null, problem: "missing" }
    return { instant: new Date(Math.min(...candidates)).toISOString(), problem: null }
  } catch {
    return { instant: null, problem: "zone" }
  }
}

export function zoned(local: string, zone: string): string | null {
  return zonedResult(local, zone).instant
}

/** The last day a phone's activity covers (04 decision 38): the usual span's last day, else its last event's day. */
export function usualLast(p: { last: string | null; usual_span?: { last: string | null } | null } | undefined): string | null {
  return p?.usual_span?.last || (p?.last ? p.last.slice(0, 10) : null)
}

/** Words for the events a phone holds on dates set apart from the rest, or null when there are none. */
export function setApartWords(label: string, span: { first: string | null; last: string | null; set_apart: number;
  set_apart_first: string | null; set_apart_last: string | null } | null | undefined): string | null {
  if (!span || !span.set_apart) return null
  const n = span.set_apart
  return `${label}: ${n.toLocaleString("en-US")} event${n === 1 ? "" : "s"} lie on dates set apart from the rest ` +
    `(${(span.set_apart_first || "").slice(0, 10)} to ${(span.set_apart_last || "").slice(0, 10)}, UTC). ` +
    `The views open on the usual span, ${span.first} to ${span.last}; any date can still be chosen.`
}

/** The local date (YYYY-MM-DD) of an instant in an IANA zone; UTC when the zone is not one the browser knows. */
export function dateIn(t: string, zone: string) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(t))
  } catch {
    return new Date(t).toISOString().slice(0, 10)
  }
}

/** The view a frozen result opens on, and the last day it covers (in its zone). A window covers the whole case and
 * has no single subject, so it opens on the Day view of its last day. */
export function snapshotView(s: Snapshot): { view: "day" | "grid" | "places"; last: string } {
  const w = s.snapshot.window
  const last = dateIn(new Date(new Date(w.end).getTime() - 1).toISOString(), w.zone)
  const view: "day" | "grid" | "places" = s.kind === "grid" ? "grid" : s.kind === "places" ? "places" : "day"
  return { view, last }
}

const DEVICE_WORDS: [string, string] = ["device event or sensor reading", "device events and sensor readings"]

/** "4 device events and sensor readings and 2 records made without use": the hidden rows counted by what they are. */
export function hiddenWords(rows: LaneRow[]): { count: number; words: string } {
  const by = new Map<string, { n: number; noun: [string, string] }>()
  for (const r of rows) {
    const n = r.total ?? r.marks.length
    const noun = r.hiddenAs || DEVICE_WORDS
    if (n > 0) by.set(noun[1], { n: (by.get(noun[1])?.n || 0) + n, noun })
  }
  const parts = Array.from(by.values(), ({ n, noun }) => `${n.toLocaleString("en-US")} ${n === 1 ? noun[0] : noun[1]}`)
  const words = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0] || ""
  return { count: Array.from(by.values()).reduce((a, b) => a + b.n, 0), words }
}

// stream families (04 5.2) whose records are the phone's own state, signal or sensors: hidden by default (07 section 5)
const DEVICE_FAMILIES = new Set(["device_events", "power", "connectivity", "network_usage", "wifi", "cell", "sensors", "locations", "logs"])
// families whose times are the messages, calls and emails the phone's lane already shows
const COPY_FAMILIES = new Set(["messages", "calls", "email"])

/** The passive lane split three ways: records made without use that a reader looks for (a bank notification, a cookie,
 * an app install) are shown; device and sensor records, and second copies of messages and calls, are counted and hidden. */
export function splitPassive(items: LaneItem[]) {
  const out = { recorded: [] as LaneItem[], device: [] as LaneItem[], copies: [] as LaneItem[] }
  for (const i of items) {
    if (i.family && DEVICE_FAMILIES.has(i.family)) out.device.push(i)
    else if (i.family && COPY_FAMILIES.has(i.family)) out.copies.push(i)
    else out.recorded.push(i)
  }
  return out
}
