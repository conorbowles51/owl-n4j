import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { instantWords } from "@/features/phones/lib/time-words"
import { analysisAPI, type ApproachResult } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"

/**
 * Approach 3, deletion and concealment timeline (05 section 6), in the shared layout (05 3.9). Rows say what the
 * records show and when it can be placed; never why anyone did anything (05 3.5).
 */
export const WHAT_IT_DOES =
  "Lists what the phones show was deleted or made unreadable and when each deletion can be placed, finds conversations that lost a larger share of messages than the rest of that app on the phone, and shows apps that can hide files or fake locations, app removals, wipes and switch-offs beside them. It does not show who deleted anything or why."

export const TABS = [
  { kind: "deleted_record", label: "Deleted records" },
  { kind: "selective_clearing", label: "Conversations with more deleted" },
  { kind: "hole", label: "Gaps in a conversation" },
  { kind: "referenced_message_absent", label: "Replies to messages not on the phone" },
  { kind: "concealment_app", label: "Hiding and location apps" },
  { kind: "app_removed", label: "Apps removed" },
  { kind: "wipe", label: "Wipes" },
  { kind: "power_off", label: "Switched off" },
  { kind: "scrambled_messages", label: "Unreadable messages" },
]

export const EXPLANATION_WORDS: Record<string, string> = {
  explained_by_setting: "A disappearing-message setting accounts for it.",
  explained_by_view_once: "Removed after being viewed once, as the record states.",
  user_deleted: "The record states it was deleted by the user of the app.",
  recalled_by_sender: "The record states the sender recalled it.",
  unexplained: "No setting or reason is recorded.",
}

const pct = (n: unknown) => `${(Number(n) * 100).toFixed(1)} percent`
const at = (iso: unknown) => (typeof iso === "string" ? instantWords(iso, "UTC") : null)

export function deletionWords(r: ApproachResult) {
  const m = r.measures as Record<string, unknown>
  const phone = (m.phone_label as string) || "this phone"
  switch (r.kind) {
    case "deleted_record": {
      const from = at(m.earliest)
      const to = at(m.latest)
      const basis = m.latest_basis
      const between = basis === "date_deleted"
        ? `Deleted at ${to}, as the record states`
        : from && to ? `Deleted at some time between ${from} and the extraction`
          : to ? "Deleted at some time before the extraction; the record has no time of its own"
            : "Deleted; the phone report gives no extraction time, so it cannot be placed"
      const ex = m.explanation ? EXPLANATION_WORDS[m.explanation as string] : undefined
      return { title: `${m.model_type === "InstantMessage" ? "Message" : String(m.model_type)} on ${phone}, ${String(m.deleted_state).toLowerCase()}`,
        line: `${between}.${ex ? ` ${ex}` : ""}` }
    }
    case "selective_clearing":
      return { title: `${m.deleted} of ${m.messages} messages deleted in one ${m.app || "app"} conversation on ${phone}`,
        line: `${pct(m.share)} here against ${pct(m.baseline_share)} across the app's other conversations on the phone (p ${Number(m.p).toPrecision(2)}, adjusted ${Number(m.q).toPrecision(2)}).${m.explained_excluded ? ` ${m.explained_excluded} deletions a setting or reason accounts for are left out.` : ""}` }
    case "hole":
      return { title: `${m.gap_days} days with no message in one ${m.app || "app"} conversation on ${phone}`,
        line: `From ${at(m.gap_start)} to ${at(m.gap_end)}. The same app recorded ${m.app_messages_elsewhere_in_gap} messages in other conversations meanwhile. A quiet period is not by itself a deletion.` }
    case "referenced_message_absent":
      return { title: `A reply on ${phone} refers to a message the phone does not hold`,
        line: m.reply_instant ? `Reply sent ${at(m.reply_instant)}.` : "The reply has no time." }
    case "concealment_app":
      return { title: `App in the ${(m.categories as string[]).join(", ")} category on ${phone}`,
        line: [m.install ? `Installed ${at(m.install)}.` : "Install time not recorded.", m.removed ? `Removed ${at(m.removed)}.` : ""].join(" ").trim() }
    case "app_removed":
      return { title: `App removed from ${phone}`, line: `Removed ${at(m.removed)}.` }
    case "wipe":
      return { title: `Wipe recorded on ${phone}`, line: m.instant ? `At ${at(m.instant)}. Shown beside deletions, never used to date them.` : "Time not recorded." }
    case "power_off":
      return { title: `${phone} switched off`, line: m.instant ? `At ${at(m.instant)}.` : "Time not recorded." }
    case "scrambled_messages":
      return { title: `${m.messages} unreadable messages in one ${m.app || "app"} conversation on ${phone}`, line: "Why they are unreadable is not established." }
    default:
      return { title: r.kind.replace(/_/g, " ") }
  }
}

export default function DeletionTimelinePage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("deletion_timeline"), [])
  return (
    <ApproachLayout caseId={caseId} title="Deleted and hidden" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-deletions" tabs={TABS} words={deletionWords} origin="phone-deletions" testId="deletion-result"
      collectLabel={(r) => deletionWords(r).title} emptyWords="Nothing of this kind on the phones in this case." />
  )
}
