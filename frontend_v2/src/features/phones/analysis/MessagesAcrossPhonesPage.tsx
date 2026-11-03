import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, messageWords } from "./message-words"

/** Approach 2, cross-phone message reconciliation (05 section 5), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "For each pair of phones whose owners are in contact: which messages are on both phones, which are deleted on one and still on the other, which the other phone has no copy of and why, and how far apart the two phones' clocks read. It does not say who wrote, read or deleted a message."

export default function MessagesAcrossPhonesPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("message_reconciliation"), [])
  return (
    <ApproachLayout caseId={caseId} title="Messages across phones" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-message-reconciliation" tabs={TABS} words={messageWords} origin="phone-message-reconciliation" testId="message-result"
      collectLabel={(r) => messageWords(r).title} emptyWords="Nothing of this kind between the phones in this case." />
  )
}
