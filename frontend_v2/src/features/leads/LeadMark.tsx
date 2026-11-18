import { SHOWN_CLASS, useIsShown } from "./highlight-store"

/** On a record row while its lead's records are shown ("Show these records"); nothing otherwise. */
export function LeadMark({ recordUid }: { recordUid: string }) {
  const on = useIsShown(recordUid)
  if (!on) return null
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${SHOWN_CLASS}`} data-lead-shown="true">In the open lead</span>
}
