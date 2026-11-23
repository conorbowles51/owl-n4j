import { Link } from "react-router-dom"
import { useSwitch } from "@/lib/ui-switches"

/** Financial's way into "Around an event" (lx-overlapviews-b C), behind corroborate-v2. */
export function AroundEventLink({ caseId }: { caseId: string }) {
  const on = useSwitch("corroborate-v2")
  if (!on) return null
  return (
    <Link to={`/cases/${caseId}/financial/around-event`} className="shrink-0 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted" data-testid="around-event-link" data-guide="around-event">
      Around an event
    </Link>
  )
}
