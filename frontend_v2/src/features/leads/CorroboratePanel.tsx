import { useEffect } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { clearPendingCorroborate, CORROBORATE_OPEN, corroborateHref, takePendingCorroborate, type CorroborateRequest } from "./open"
import { clearLeadRecords, useShownLead } from "./highlight-store"
import { EMPTY_SCOPE, scopeHref } from "@/features/phones/ui/scope"

/**
 * Corroborate from anywhere (lx-corroredo A): pressing Corroborate on any screen opens the Corroborate page with the
 * question filled from the selection. The page is where answers are read; nothing opens over the page any more, and
 * nothing runs until a person presses Ask. Mounted once in the case layout, with the bar that shows a lead's records.
 */
export function CorroborateOpener() {
  const navigate = useNavigate()
  useEffect(() => {
    const go = (req: CorroborateRequest | null) => {
      if (req) navigate(corroborateHref(req.caseId, { from: "selection" }))
    }
    go(takePendingCorroborate())
    const open = (e: Event) => {
      clearPendingCorroborate() // taken here: an opener mounted later never moves to the page by itself
      go((e as CustomEvent<CorroborateRequest>).detail)
    }
    window.addEventListener(CORROBORATE_OPEN, open)
    return () => window.removeEventListener(CORROBORATE_OPEN, open)
  }, [navigate])
  return <ShownLeadBar />
}

const LEAD_PAGES: [string, string][] = [["conversations", "Conversations"], ["timeline", "Timeline"], ["map", "Map"]]

/** Conversations opens its first thread unless a record is named; naming the lead's first phone record opens every
 * message on the lead's days instead, with that record beside them. */
function firstPhoneRecord(refs: Set<string>): Record<string, string> {
  for (const r of refs) if (r.startsWith("phone_record:")) return { record: r.slice("phone_record:".length) }
  return {}
}

/** The lead's days as a phone scope window (null when the lead has no dates: the page then opens on everything). */
function leadWindow(period?: { from?: string; to?: string }): { from: string; to: string } | null {
  const from = period?.from ?? period?.to
  const to = period?.to ?? period?.from
  if (!from || !to) return null
  // A lead's days are UTC dates and the pages read days in the case's zone: a night at 22:00 in New York is the next
  // day in UTC, so the window opens a day earlier to hold the first night whole.
  const d = new Date(`${from.slice(0, 10)}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - 1)
  return { from: d.toISOString().slice(0, 10), to: to.slice(0, 10) }
}

/** While a lead's records are shown, a bar says so on every page, with links to the lead's days on Conversations,
 * the timeline and the map (in-page links, so the marks stay), and the way to stop. */
function ShownLeadBar() {
  const shown = useShownLead()
  if (!shown) return null
  return (
    <div className="fixed bottom-3 left-1/2 z-50 flex max-w-[95vw] -translate-x-1/2 flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl border bg-background px-4 py-2 text-xs shadow-lg sm:flex-nowrap sm:rounded-full" role="status">
      <span className="min-w-0 truncate">Showing {shown.refs.size.toLocaleString()} records of the lead “{shown.title}”</span>
      {shown.caseId && (
        <span className="flex shrink-0 gap-2" aria-label="Open the lead's days">
          {LEAD_PAGES.map(([path, words]) => (
            <Link key={path} className="underline" to={scopeHref(`/cases/${shown.caseId}/${path}`, { ...EMPTY_SCOPE, window: leadWindow(shown.period) },
                                                                 path === "conversations" ? firstPhoneRecord(shown.refs) : {})}>{words}</Link>
          ))}
        </span>
      )}
      <Button size="sm" variant="ghost" onClick={() => clearLeadRecords()}>Close</Button>
    </div>
  )
}
