import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, intentAnchor, intentWords } from "./intent-words"
import { NOT_INCLUDED } from "./TypedWordsPage"

/** Approach 9, intent and research, the matching view (05 section 12), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "For each phone: the searches and visited pages whose text, title or address matches names, phone numbers, account endings, account holders or counterparties already in the case, with the time each records. A page records its last visit only. It does not say why anything was searched for or who searched."

export default function IntentPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("intent"), [])
  return (
    <ApproachLayout caseId={caseId} title="Searches and pages" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-intent" tabs={TABS} words={intentWords} anchorRelation={intentAnchor} origin="phone-intent" testId="intent-result"
      collectLabel={(r) => intentWords(r).title} emptyWords="No search or visited page on the phones matches the case's names, numbers or accounts."
      extra={<p className="text-sm text-muted-foreground">{NOT_INCLUDED} Every search and page stays in each phone's own record lists.</p>} />
  )
}
