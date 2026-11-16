import { Link, useLocation } from "react-router-dom"
import { phoneLayersEnabled } from "../lib/phone-layers"
import { useCasePhones } from "./use-case-phones"

/**
 * A page that belongs to one phone keeps that phone. This leads from it to the case-level views, where the phone is
 * on and the others of the case can be switched on beside it; the address carries this page's own filters.
 */
export function AddOtherPhones({ caseId, extraction }: { caseId: string; extraction: string }) {
  const phones = useCasePhones(caseId)
  const { search } = useLocation()
  if (!phoneLayersEnabled() || phones.length < 2) return null
  const q = new URLSearchParams(search)
  q.set("phones", extraction)
  q.delete("record")
  const to = (view: string) => `/cases/${encodeURIComponent(caseId)}/${view}?${q.toString()}`
  return (
    <p className="text-sm" data-testid="add-other-phones">
      This page shows one phone. Add other phones in{" "}
      <Link className="underline" to={to("conversations")}>Conversations</Link>,{" "}
      <Link className="underline" to={to("timeline")}>Timeline</Link> or <Link className="underline" to={to("map")}>Map</Link>.
    </p>
  )
}
