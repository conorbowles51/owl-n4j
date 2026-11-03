import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, commonWords } from "./common-words"

/** Approach 14, common contacts (05 section 16a), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "For each pair of phone owners in the case: the people both are in contact with, on any phone in the case, with the calls, messages and emails on each side and the first and last of them. A person saved as a contact with no contact seen on one side is listed apart. It does not say how the two owners are connected."

export default function CommonContactsPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("common_contacts"), [])
  return (
    <ApproachLayout caseId={caseId} title="Common contacts" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-common-contacts" tabs={TABS} words={commonWords} origin="phone-common-contacts" testId="common-result"
      collectLabel={(r) => commonWords(r).title} emptyWords="No person is in contact with two phone owners in this case, or the case holds one owner." />
  )
}
