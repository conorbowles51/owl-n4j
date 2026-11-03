import { useMemo } from "react"
import { Link, useParams } from "react-router-dom"
import { instantWords } from "@/features/phones/lib/time-words"
import { analysisAPI, type ApproachResult } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"

/** Approach 11, relationships over time (05 section 14), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "For each person on each phone: when the phone saved them as a contact, what each phone calls them, when calls and messages with them began and ended, how many there were each month, and the weeks where the amount of contact rose or fell. It does not show what the relationship was, and contact through apps the extraction does not hold is not counted."

export const TABS = [
  { kind: "relationship", label: "People on each phone" },
  { kind: "volume_change", label: "Weeks where contact rose or fell" },
]

type M = Record<string, unknown>
const day = (iso: unknown) => (typeof iso === "string" && iso ? instantWords(iso, "UTC").replace(/ \d{1,2}:\d{2}.*$/, "") : null)

function firstLast(m: M): string {
  const first = (m.first || {}) as Record<string, string | null>
  const last = (m.last || {}) as Record<string, string | null>
  const f = Object.values(first).filter(Boolean).sort()[0]
  const l = Object.values(last).filter(Boolean).sort().slice(-1)[0]
  if (!f) return "No call or message with a time."
  return `First ${day(f)}, last ${day(l)}.`
}

export function relationshipWords(r: ApproachResult) {
  const m = r.measures as M
  const who = ((m.names_here as string[]) || [])[0] || (m.display as string) || "Unnamed"
  const phone = (m.phone_label as string) || "this phone"
  if (r.kind === "volume_change") {
    const verb = r.strength === "rise" ? "rose" : "fell"
    return { title: `Contact with ${who} on ${phone} ${verb} from the week of ${m.week_start}`,
      line: `About ${m.rate_before} a week for ${m.weeks_before} weeks, then about ${m.rate_after} a week for ${m.weeks_after} weeks.` }
  }
  const elsewhere = Object.entries((m.names_elsewhere || {}) as Record<string, string[]>)
    .map(([p, names]) => `${p} calls them ${names.join(" or ")}`)
  const saved = m.saved ? `Saved as a contact ${day(m.saved)}.` : (Number(m.contact_cards) > 0 ? "Saved as a contact; the phone recorded no saved time." : "Not saved as a contact.")
  const changed = m.modified ? ` Contact last changed ${day(m.modified)}.` : ""
  return {
    title: `${who} on ${phone}: ${Number(m.communications).toLocaleString("en-US")} calls, messages and emails`,
    line: `${firstLast(m)} ${saved}${changed}${elsewhere.length ? ` ${elsewhere.join("; ")}.` : ""}${Number(m.untimed) ? ` ${m.untimed} have no time.` : ""}`,
  }
}

export default function RelationshipsPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("relationships"), [])
  return (
    <ApproachLayout caseId={caseId} title="Relationships over time" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-relationships" tabs={TABS} words={relationshipWords} origin="phone-relationships" testId="relationship-result"
      collectLabel={(r) => relationshipWords(r).title} emptyWords="No calls, messages or contacts with anyone on the phones in this case."
      extra={<p className="text-sm">To test a statement such as "no contact after a date", use <Link className="underline" to={`/cases/${caseId}/phone-patterns`}>Check a statement</Link> in Patterns.</p>}
      openLink={(r) => {
        const keys = ((r.measures as M).identity_keys as string[]) || []
        return keys.length ? { to: `/cases/${encodeURIComponent(caseId)}/conversations?${new URLSearchParams({ tab: "people", people: keys.join(",") }).toString()}`, label: "Open their calls and messages" } : null
      }} />
  )
}
