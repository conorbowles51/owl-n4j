import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, deletionWords } from "./deletion-words"

/**
 * Approach 3, deletion and concealment timeline (05 section 6), in the shared layout (05 3.9). Rows say what the
 * records show and when it can be placed; never why anyone did anything (05 3.5).
 */
export const WHAT_IT_DOES =
  "Lists what the phones show was deleted or made unreadable and when each deletion can be placed, finds conversations that lost a larger share of messages than the rest of that app on the phone, and shows apps that can hide files or fake locations, app removals, wipes and switch-offs beside them. It does not show who deleted anything or why."

export default function DeletionTimelinePage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("deletion_timeline"), [])
  return (
    <ApproachLayout caseId={caseId} title="Deleted and hidden" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-deletions" tabs={TABS} words={deletionWords} origin="phone-deletions" testId="deletion-result"
      collectLabel={(r) => deletionWords(r).title} emptyWords="Nothing of this kind on the phones in this case." />
  )
}
