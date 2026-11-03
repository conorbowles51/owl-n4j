import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "between_owners", label: "Between phone owners" },
  { kind: "cell", label: "Owners and other people" },
]

const CHANNEL: Record<string, [string, string]> = { message: ["message", "messages"], call: ["call", "calls"], email: ["email", "emails"] }
const STATUS: Record<string, string> = { Established: "connected", Missed: "missed", Rejected: "rejected", Canceled: "cancelled", BusyLine: "busy", NotEstablishedUnknownReason: "not connected, reason not recorded" }
const n = (v: number) => v.toLocaleString("en-US")
type M = { from_display: string; to_display: string; total: number; by_channel: Record<string, number>; calls_by_status: Record<string, number>; connected_call_seconds: number; reverse_total: number; unmatched_owner_copies: number }

export function matrixWords(r: ApproachResult) {
  const m = r.measures as unknown as M
  const parts = Object.entries(m.by_channel).map(([k, v]) => `${n(v)} ${CHANNEL[k] ? CHANNEL[k][v === 1 ? 0 : 1] : k}`)
  const calls = Object.entries(m.calls_by_status || {}).map(([k, v]) => `${n(v)} ${STATUS[k] || k}`)
  const mins = Math.round((m.connected_call_seconds || 0) / 60)
  const line = [
    calls.length ? `Calls: ${calls.join(", ")}${mins ? `; ${n(mins)} ${mins === 1 ? "minute" : "minutes"} connected` : ""}.` : "",
    `In the other direction: ${n(m.reverse_total)}.`,
    m.unmatched_owner_copies ? `${n(m.unmatched_owner_copies)} ${m.unmatched_owner_copies === 1 ? "message" : "messages"} between the two owners could not be matched across their phones and may be counted on each.` : "",
  ].filter(Boolean).join(" ")
  return { title: `From ${m.from_display} to ${m.to_display}: ${parts.join(", ")}`, line }
}
