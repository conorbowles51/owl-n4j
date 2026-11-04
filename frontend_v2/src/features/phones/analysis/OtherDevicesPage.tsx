import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { StrengthLine } from "./StrengthLine"
import { TABS, otherDevicesWords } from "./other-devices-words"

/**
 * Approach 6, other devices and accounts in play (05 section 9), in the shared layout (05 3.9): every key two or more
 * phones share, graded strong to faint with its reasons, and per phone its devices, networks, accounts, services
 * without an app and remote sessions. Built with no count gate (Neil, 2026-11-04).
 */
export const WHAT_IT_DOES =
  "The WiFi networks, Bluetooth devices, accounts, saved logins and web services each phone shows, and which of them more than one phone in the case shares, each with how well it matches and how much each phone holds behind it. A shared device or network is not proof the phones were together or had one user."

export const OLD_RULE = "The plan first listed shared keys only once a case had 5 strong ones."
export const RULE = "Strength: a hardware or SIM identifier strong, a username on one service moderate, a name or web service weak, one level lower for a Bluetooth device only detected nearby or a name most phones hold. These levels are rules of thumb, not measured on this case."

export default function OtherDevicesPage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("other_devices"), [])
  return (
    <ApproachLayout caseId={caseId} title="Devices and accounts across phones" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-other-devices" tabs={TABS} words={otherDevicesWords} origin="phone-other-devices" testId="other-devices-result"
      collectLabel={(r) => otherDevicesWords(r).title} emptyWords="Nothing of this kind for the phones in this case."
      runExtra={(run) => <StrengthLine run={run} prefix="shared_" noun={["key shared across phones", "keys shared across phones"]} oldRule={OLD_RULE} rule={RULE} />} />
  )
}
