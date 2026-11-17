import { useQuery } from "@tanstack/react-query"
import { corroborateAPI, type Scope } from "./api"
import { presetScope, SPAN_WORDS, type Span } from "./preset-windows"

/**
 * Preset windows from incident dates (lx-corrorest E): the dates the case's theories and findings state in their own
 * words, each with the words it was read from, and "± 1 hour / day / week" buttons. A date with no time says why the
 * hour button is off.
 */
export function IncidentPresets({ caseId, onPick }: { caseId: string; onPick: (s: Scope) => void }) {
  const q = useQuery({ queryKey: ["corroborate-incidents", caseId], queryFn: () => corroborateAPI.incidents(caseId), staleTime: 60_000 })
  if (q.isLoading) return <p role="status" className="text-xs text-muted-foreground">Reading incident dates…</p>
  if (q.isError) return <p role="alert" className="text-xs">Incident dates could not be read, so no preset windows are offered.</p>
  const list = q.data?.incidents ?? []
  if (!list.length) return <p className="text-xs text-muted-foreground">No theory or finding states a date, so there are no incident presets. Use From and To.</p>
  return (
    <div className="mt-1 flex flex-col gap-1 text-xs">
      <span className="text-muted-foreground">Round an incident (dates stated in theories and findings)</span>
      <ul className="flex flex-col gap-1">
        {list.slice(0, 12).map((inc) => (
          <li key={`${inc.entry_id}:${inc.date}:${inc.time}`} className="flex flex-wrap items-center gap-1">
            <span title={`In "${inc.title || inc.entry_type}"`}>{inc.date}{inc.time ? ` ${inc.time}` : ""} <span className="text-muted-foreground">from "{inc.words}"</span></span>
            {(Object.keys(SPAN_WORDS) as Span[]).map((span) => {
              const next = presetScope(inc, span)
              return (
                <button key={span} type="button" disabled={!next} className="rounded border px-1 disabled:opacity-50"
                  title={next ? undefined : "This date has no time, so a window of hours cannot be placed."}
                  onClick={() => next && onPick(next)}>± {SPAN_WORDS[span]}</button>
              )
            })}
          </li>
        ))}
      </ul>
      {list.length > 12 && <span className="text-muted-foreground">{list.length - 12} more dates are not shown; use From and To.</span>}
    </div>
  )
}
