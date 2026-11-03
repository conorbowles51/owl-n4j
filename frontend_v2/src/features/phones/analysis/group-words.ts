import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"

export const TABS = [{ kind: "group_roles", label: "Group chats" }]

const ACTION_WORDS: Record<string, string> = {
  ParticipantAdded: "participant added", ParticipantJoined: "participant joined", ParticipantLeft: "participant left",
  ParticipantRemoved: "participant removed", ChatNameChanged: "group name changed", ChatImageChanged: "group picture changed",
  Unknown: "change of unknown kind",
}

interface Change { action: string; instant: string | null; participants: string[] }

export function groupWords(r: ApproachResult) {
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
