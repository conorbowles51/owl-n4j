import { useMemo } from "react"
import { Link, useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, relationshipWords } from "./relationship-words"

/** Approach 11, relationships over time (05 section 14), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "For each person on each phone: when the phone saved them as a contact, what each phone calls them, when calls and messages with them began and ended, how many there were each month, and the weeks where the amount of contact rose or fell. It does not show what the relationship was, and contact through apps the extraction does not hold is not counted."

export default function RelationshipsPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("relationships"), [])
  return (
    <ApproachLayout caseId={caseId} title="Relationships over time" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-relationships" tabs={TABS} words={relationshipWords} origin="phone-relationships" testId="relationship-result"
      collectLabel={(r) => relationshipWords(r).title} emptyWords="No calls, messages or contacts with anyone on the phones in this case."
      extra={<p className="text-sm">To test a statement such as "no contact after a date", use <Link className="underline" to={`/cases/${caseId}/phone-patterns`}>Check a statement</Link> in Patterns.</p>}
      openLink={(r) => {
        const keys = (r.measures.identity_keys as string[] | undefined) || []
        const ext = r.measures.extraction_id as string | undefined
        return keys.length ? { to: `/cases/${encodeURIComponent(caseId)}/conversations?${new URLSearchParams({ tab: "people", people: keys.join(","), ...(ext ? { phones: ext } : {}) }).toString()}`, label: "Open their calls and messages" } : null
      }} />
  )
}
