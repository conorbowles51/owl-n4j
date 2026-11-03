import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { patternAPI } from "@/features/pattern/api"
import { WindowPanel } from "@/features/pattern/components/WindowPanel"

/**
 * Approach 13, the incident window (05 section 16; 07 J-5): every phone in the case around one anchor, one lane group
 * per phone with its availability, so no data reads as no data. The same view opens from a statement (its window and
 * zone), a key date, a record and the Timeline; here the anchor can also be typed. Default window: 1 hour either side
 * (05 16.6, measured).
 */
export const WHAT_IT_DOES =
  "Everything each phone in the case recorded around one moment, side by side, with the hours each phone holds no data shown as no data. Choose the moment, or open this from a statement, a key date, a record or the Timeline."

export default function IncidentWindowPage() {
  const { id: caseId = "" } = useParams()
  const [search, setSearch] = useSearchParams()
  const at = search.get("at")
  const day = search.get("day")
  const start = search.get("start")
  const end = search.get("end")
  const zone = search.get("zone") || "case"
  const label = search.get("label")
  const [typed, setTyped] = useState("")
  const subjects = useQuery({ queryKey: ["pattern-subjects", caseId], queryFn: () => patternAPI.subjects(caseId), enabled: !!caseId && !at && !day && !(start && end) })
  const latest = subjects.data?.extractions.map((e) => e.last).filter(Boolean).sort().pop() || null
  const range = start && end ? { start, end } : null
  const anchor = range ? range.start : day ? `${day}T00:00:00Z` : at || latest
  const named = range ? `the window of ${label || "the statement"} (zone: ${zone === "case" ? "the case's" : zone})`
    : day ? `the day ${day}` : at ? (label || "the chosen moment") : "the latest moment on the case's phones (no moment chosen yet)"
  function open() {
    const d = new Date(typed)
    if (Number.isNaN(d.getTime())) return
    setSearch({ at: d.toISOString(), label: "the typed moment" })
  }
  return (
    <div className="space-y-4 p-4" data-testid="incident-window-page">
      <h1 className="text-lg font-semibold">Incident window</h1>
      <p data-part="what">{WHAT_IT_DOES}</p>
      <div data-part="run" className="flex flex-wrap items-end gap-2 text-sm">
        <label className="flex flex-col">Moment (your browser's time)
          <input type="datetime-local" value={typed} onChange={(e) => setTyped(e.target.value)} className="rounded border bg-background px-2 py-1" />
        </label>
        <Button size="sm" onClick={open} disabled={!typed}>Open the window</Button>
      </div>
      <p data-part="coverage" className="text-sm">Around {named}.</p>
      <section data-part="results" aria-label="Results">
        {subjects.isLoading && <p className="text-sm">Finding the latest moment on the phones…</p>}
        {!anchor && !subjects.isLoading && <p className="text-sm">The case's phones hold no timed record yet. Choose a moment above.</p>}
        {anchor && <WindowPanel key={`${anchor}|${day}|${range?.end}|${zone}`} caseId={caseId} at={anchor} day={day} range={range} caseEvents={[]} zone={zone} exportable />}
      </section>
    </div>
  )
}
