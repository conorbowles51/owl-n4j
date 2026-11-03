import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, deviceWords } from "./device-words"

/**
 * Approach 5, who used which phone: the complementary-use part (05 section 8.3 steps 1, 3 and 5), in the shared layout
 * (05 3.9). Where two phones were together is not offered: its gate failed (05 8.6). The screen gives numbers, never
 * who used a phone.
 */
export const WHAT_IT_DOES =
  "For each pair of phones: the phone numbers, SIM cards, accounts and WiFi networks they have in common, and, over the days both were in use, how often each was used while the other was not. For each phone: signs that more than one person used it. It does not say who used either phone."

export const NOT_BUILT = "Whether two phones were in the same place is not offered here: no two phones in the measured cases were placed in the same quarter hour often enough to compare."

export default function DeviceUsersPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("device_users"), [])
  return (
    <ApproachLayout caseId={caseId} title="Who used which phone" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-device-users" tabs={TABS} words={deviceWords} origin="phone-device-users" testId="device-user-result"
      collectLabel={(r) => deviceWords(r).title} emptyWords="Nothing of this kind for the phones in this case."
      extra={<p className="text-sm text-muted-foreground">{NOT_BUILT}</p>} />
  )
}
