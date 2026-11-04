import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, switchWords } from "./switch-words"

/** Approach 16, number switching (05 section 16c), in the shared layout (05 3.9). */
export const WHAT_IT_DOES =
  "Numbers or accounts whose contact stops while another, in contact with mostly the same people, starts soon after: the gap, how many counterparts they share, and any saved contact entry or name that holds both. It does not say the two are the same person, and it joins nothing."

export default function NumberSwitchingPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("number_switching"), [])
  return (
    <ApproachLayout caseId={caseId} title="Possible number changes" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-number-switching" tabs={TABS} words={switchWords} origin="phone-number-switching" testId="switch-result"
      runExtra={(run) => run.left_out_words ? <p className="text-sm" data-testid="switch-left-out">{run.left_out_words}</p> : null}
      collectLabel={(r) => switchWords(r).title} emptyWords="No number or account stops while another with mostly the same counterparts starts within the gap." />
  )
}
