import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { StrengthLine } from "./StrengthLine"
import { TABS, plansWords } from "./plans-words"

/**
 * Approach 10, plans and self-reported places (05 section 13), in the shared layout (05 3.9): every calendar entry,
 * check-in and note; a placed entry or check-in compared with the phone's own location in its window. Built with no
 * count gate (Neil, 2026-11-04).
 */
export const WHAT_IT_DOES =
  "What the phones' calendars, check-ins and notes say was planned or reported, and, where the phone itself places an entry or check-in, whether the phone's own location at that time agrees. A calendar entry is a plan, not attendance; a check-in can be made from elsewhere."

export const OLD_RULE = "The plan first compared plans with location only once a case had 20 placed entries."
export const RULE = "Strength: both sides stating their accuracy strong, one accuracy assumed moderate, locations that disagree weak, not compared faint. These levels are rules of thumb, not measured on this case. A place written as text is not placed: no offline place list is installed."

export default function PlansPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("plans"), [])
  return (
    <ApproachLayout caseId={caseId} title="Plans and check-ins against location" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-plans" tabs={TABS} words={plansWords} origin="phone-plans" testId="plans-result"
      collectLabel={(r) => plansWords(r).title} emptyWords="Nothing of this kind for the phones in this case."
      runExtra={(run) => <StrengthLine run={run} prefix="by_strength_" noun={["entry, check-in or note", "entries, check-ins and notes"]} oldRule={OLD_RULE} rule={RULE} />} />
  )
}
