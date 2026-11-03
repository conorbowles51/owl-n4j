import { Link } from "react-router-dom"
import type { ReplacedState } from "./replaced-links"

/** 07 CO-9a and CO-9b: a link to a record of a replaced phone report says so, and offers the record with the equal
 * natural key in the report that replaced it, or says why none is offered. The link itself is never moved. */
export function ReplacedLinkNote({ caseId, state }: { caseId: string; state: ReplacedState | undefined }) {
  if (!state?.replaced) return null
  const to = state.newer_record_uid ? `/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(state.newer_record_uid)}` : null
  return (
    <p className="text-[10px] text-muted-foreground" data-testid="replaced-link-note">
      {state.words}
      {to && <> <Link className="underline" to={to}>Open the matching record</Link></>}
    </p>
  )
}
