import { ApiError } from "@/lib/api-client"
import { phoneLinkHref } from "@/features/phones/phone-links"
import type { DayResponse, KeyDate, LaneItem } from "./api"
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
export function bandsFromHours(hours: { hour_utc: string; state: string; words: string }[]): LaneBand[] {
  const out: LaneBand[] = []
  for (const h of hours) {
    const end = new Date(new Date(h.hour_utc).getTime() + 3600_000).toISOString()
    const last = out[out.length - 1]
    if (last && last.state === h.state && last.end === new Date(h.hour_utc).toISOString()) last.end = end
    else out.push({ start: new Date(h.hour_utc).toISOString(), end, state: h.state, words: h.words })
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
      note: k === "passive" && d.passive_as_hourly_counts ? d.limit_words || undefined : undefined,
      marks: items.map((i) => ({ key: `${i.ref_kind}:${i.id}`, at: i.at, end: i.end, label: itemLabel(i),
        detail: [i.strength && `strength ${i.strength}`, i.actor && `actor ${i.actor}`, i.source_app, i.phone, ...(i.flags || [])].filter(Boolean).join(" · "),
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
