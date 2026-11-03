import { Link } from "react-router-dom"
import type { AcrossBadge, AcrossRun } from "./across-badges"

/** One message's badges from Messages across phones (05 section 5.4), with the reasons and the other copy. */
export function AcrossBadges({ caseId, badges }: { caseId: string; badges: AcrossBadge[] }) {
  if (!badges.length) return null
  return (
    <span className="flex flex-wrap items-center gap-2" data-testid="across-badges">
      {badges.map((b) => (
        <span key={b.words} className="rounded border border-border px-1 py-px">
          {b.words}
          {b.reasons.length > 0 && <span className="text-muted-foreground"> ({b.reasons.join(" ")})</span>}
          {b.other_record_uid && <> <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(b.other_record_uid)}`}>Open the copy on {b.other_phone}</Link></>}
        </span>
      ))}
    </span>
  )
}

/** Where the badges come from, and whether the phones changed since. */
export function AcrossBadgesSource({ run }: { run: AcrossRun | null }) {
  if (!run) return null
  return (
    <p className="px-2 text-xs text-muted-foreground" data-testid="across-badges-source">
      "Also on" and "Only on this phone" come from the latest run of Messages across phones; a message it did not compare has no badge.
      {!run.current && " The phones have changed since that run; run Messages across phones again for current badges."}
    </p>
  )
}
