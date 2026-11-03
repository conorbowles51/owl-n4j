import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { instantWords } from "@/features/phones/lib/time-words"
import { analysisAPI, type ApproachResult } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"

/**
 * Approach 4, group roles (05 section 7.3 step 5), in the shared layout (05 3.9). Read times and reply latency are
 * not built: their gate failed (05 7.6), and the screen says so.
 */
export const WHAT_IT_DOES =
  "For each group chat on the phones: who the phone report flags as a group admin at extraction, and the membership changes it records, with their time where one was recorded and the participant each names. It does not show who made a change, and it does not show when messages were read."

export const NOT_BUILT =
  "Read times and reply delays are not listed here: too few messages on the measured phones carry a read time to compare. A message's own read time is shown with it in Conversations."

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

export default function GroupRolesPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("awareness"), [])
  return (
    <ApproachLayout caseId={caseId} title="Group admins and membership" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-groups" tabs={TABS} words={groupWords} origin="phone-groups" testId="group-result"
      collectLabel={(r) => groupWords(r).title} emptyWords="No group chat on the phones records an admin or a membership change."
      extra={<p className="text-sm text-muted-foreground">{NOT_BUILT}</p>} />
  )
}
