import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { GRADED_TABS, TABS, groupWords } from "./group-words"
import { strengthCounts } from "./strength-words"

/**
 * Approach 4, knowledge and awareness (05 section 7.3 steps 1 to 5), in the shared layout (05 3.9). Every step runs
 * on every phone; the counts behind the results are shown (coverage notes) and each read result carries its strength.
 */
export const WHAT_IT_DOES =
  "For each conversation on the phones: when the owner read or played incoming messages and the other side read outgoing ones, as far as the records hold read times; how long the owner took to reply in one-to-one conversations; messages the owner read with no reply; and messages still marked unread. For each group chat: who the phone report flags as an admin at extraction, and the membership changes it records. It does not show who made a change, and no read time does not mean a message was not read."

export const TITLE = "Reading, replies and group roles"

export default function GroupRolesPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("awareness"), [])
  return (
    <ApproachLayout caseId={caseId} title={TITLE} whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-groups" tabs={TABS} words={groupWords} origin="phone-groups" testId="group-result"
      collectLabel={(r) => groupWords(r).title} emptyWords="Nothing of this kind on the phones in this case."
      runExtra={(run) => <p className="text-sm" data-testid="group-result-strengths">By strength: {strengthCounts(run, GRADED_TABS).join("; ")}.</p>} />
  )
}
