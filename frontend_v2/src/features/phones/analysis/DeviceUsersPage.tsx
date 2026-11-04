import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { GRADED_TABS, TABS, deviceWords } from "./device-words"
import { strengthCounts } from "./strength-words"

/**
 * Approach 5, who used which phone (05 section 8.3 steps 1 to 5), in the shared layout (05 3.9). Together and apart
 * run on every pair with a shared quarter hour; the counts behind them are shown (coverage notes) and each carries
 * its strength. The screen gives numbers, never who used a phone.
 */
export const WHAT_IT_DOES =
  "For each pair of phones: the phone numbers, SIM cards, accounts and WiFi networks they have in common; over the days both were in use, how often each was used while the other was not; in the quarter hours both were placed, whether they were together or apart; and when one was used while they were apart. For each phone: signs that more than one person used it. It does not say who used either phone."

export default function DeviceUsersPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("device_users"), [])
  return (
    <ApproachLayout caseId={caseId} title="Who used which phone" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-device-users" tabs={TABS} words={deviceWords} origin="phone-device-users" testId="device-user-result"
      collectLabel={(r) => deviceWords(r).title} emptyWords="Nothing of this kind for the phones in this case."
      runExtra={(run) => <p className="text-sm" data-testid="device-user-result-strengths">By strength: {strengthCounts(run, GRADED_TABS).join("; ")}.</p>} />
  )
}
