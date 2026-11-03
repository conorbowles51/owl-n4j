import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, groupWords } from "./group-words"

/**
 * Approach 4, group roles (05 section 7.3 step 5), in the shared layout (05 3.9). Read times and reply latency are
 * not built: their gate failed (05 7.6), and the screen says so.
 */
export const WHAT_IT_DOES =
  "For each group chat on the phones: who the phone report flags as a group admin at extraction, and the membership changes it records, with their time where one was recorded and the participant each names. It does not show who made a change, and it does not show when messages were read."

export const NOT_BUILT =
  "Read times and reply delays are not listed here: too few messages on the measured phones carry a read time to compare. A message's own read time is shown with it in Conversations."

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
