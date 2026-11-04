import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"
import { LEVEL_WORDS } from "./strength-words"

export const TABS = [
  { kind: "group_roles", label: "Group chats" },
  { kind: "read_events", label: "Read times" },
  { kind: "reply_latency", label: "Reply times" },
  { kind: "read_without_reply", label: "Read, no reply" },
  { kind: "unread", label: "Unread" },
]

/** The tabs graded on the one scale (group chats keep their own timed or untimed label). */
export const GRADED_TABS = TABS.filter((t) => t.kind !== "group_roles")

const ACTION_WORDS: Record<string, string> = {
  ParticipantAdded: "participant added", ParticipantJoined: "participant joined", ParticipantLeft: "participant left",
  ParticipantRemoved: "participant removed", ChatNameChanged: "group name changed", ChatImageChanged: "group picture changed",
  Unknown: "change of unknown kind",
}

interface Change { action: string; instant: string | null; participants: string[] }

interface Quart { n: number; median_s: number; q1_s: number; q3_s: number }

export function duration(s: number): string {
  if (s < 120) return `${Math.round(s)} seconds`
  if (s < 7200) return `${Math.round(s / 60)} minutes`
  if (s < 172800) return `${(s / 3600).toFixed(1)} hours`
  return `${(s / 86400).toFixed(1)} days`
}

const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")

/** Steps 1 to 4 (05 7.3): numbers about one conversation, with the strength first. Never says a message was or was
 * not read beyond what the record holds. */
function readWords(r: ApproachResult) {
  const m = r.measures as Record<string, unknown> & { correspondent?: { display?: string }; latency?: Quart | null; read_to_reply?: Quart | null }
  const who = m.correspondent?.display || "an unnamed correspondent"
  const where = `${m.title ? `${m.title}, ` : ""}${who} on ${m.phone_label || "this phone"}`
  const lv = LEVEL_WORDS[r.strength] || r.strength
  if (r.kind === "reply_latency") {
    const q = m.latency!
    const rr = m.read_to_reply ? ` From the owner's read time: median ${duration(m.read_to_reply.median_s)} over ${n(m.read_to_reply.n)}.` : " No owner read time on these messages."
    return { title: `${lv}. Reply times with ${where}`, line: `${n(q.n)} ${q.n === 1 ? "reply" : "replies"}; median ${duration(q.median_s)}, middle half ${duration(q.q1_s)} to ${duration(q.q3_s)}.${rr}` }
  }
  if (r.kind === "read_without_reply") {
    return { title: `${lv}. Read with no reply: ${where}`, line: `${n(m.without_reply)} of ${n(m.read_incoming)} messages the owner read had no message back within ${n(m.window_hours)} hours${m.window_basis === "case_95th_percentile" ? " (the case's 95th percentile of reply times)" : ""}.` }
  }
  if (r.kind === "unread") {
    return { title: `${lv}. Unread at extraction: ${where}`, line: `${n(m.unread)} incoming ${Number(m.unread) === 1 ? "message is" : "messages are"} marked unread.` }
  }
  return { title: `${lv}. Read times: ${where}`,
    line: `Incoming ${n(m.incoming)}: read by the owner ${n(m.incoming_owner_read)}, played ${n(m.incoming_owner_played)}. Outgoing ${n(m.outgoing)}: read by the other side ${n(m.outgoing_recipient_read)}, played ${n(m.outgoing_recipient_played)}, delivered ${n(m.outgoing_recipient_delivered)}.` }
}

export function groupWords(r: ApproachResult) {
  if (r.kind !== "group_roles") return readWords(r)
  const m = r.measures as { phone_label?: string; title?: string | null; participants?: number; admins?: { display: string }[]; changes?: Change[] }
  const admins = (m.admins || []).map((a) => a.display)
  const changes = (m.changes || []).map((c) => {
    const who = c.participants.length ? `, participant named: ${c.participants.join(", ")}` : ""
    const when = c.instant ? instantWords(c.instant, "UTC") : "time not recorded"
    return `${ACTION_WORDS[c.action] || c.action} (${when}${who})`
  })
  return {
    title: `${m.title || "Group chat"} on ${m.phone_label || "this phone"}, ${m.participants ?? 0} participants`,
    line: [admins.length ? `Admin at extraction: ${admins.join(", ")}.` : "No admin flag recorded.",
      changes.length ? `Changes: ${changes.join("; ")}.` : "No membership change recorded."].join(" "),
  }
}
