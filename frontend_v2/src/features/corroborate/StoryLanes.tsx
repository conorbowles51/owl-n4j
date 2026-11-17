import { useQuery } from "@tanstack/react-query"
import { relationAPI } from "@/features/relations/api"

const KIND_CLASS: Record<string, string> = {
  message: "bg-sky-100 text-sky-900", call: "bg-indigo-100 text-indigo-900", payment: "bg-emerald-100 text-emerald-900",
  payment_alert: "bg-emerald-100 text-emerald-900", doc_row: "bg-amber-100 text-amber-900", position: "bg-rose-100 text-rose-900",
  media_position: "bg-rose-100 text-rose-900",
}

function when(at: string, dayOnly: boolean): string {
  return dayOnly ? at.slice(0, 10) : at.slice(0, 16).replace("T", " ") + " UTC"
}

/** One lane per person for one instance: the records the grid cites for it, numbered in the order they happened. */
export function StoryLanes({ caseId, runId, instance, onClose }: { caseId: string; runId: string; instance: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["relation-lanes", caseId, runId, instance], queryFn: () => relationAPI.lanes(caseId, runId, instance) })
  return (
    <section aria-label="Story lanes" className="rounded border p-3" data-testid="story-lanes">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-semibold">What happened, person by person{q.data ? `: ${q.data.instance.label}` : ""}</h3>
        <button type="button" className="text-sm underline" onClick={onClose}>Close</button>
      </div>
      {q.isLoading && <p role="status" className="text-sm">Reading the records for this instance…</p>}
      {q.isError && <p role="alert" className="text-sm">The lanes could not be read: {q.error instanceof Error ? q.error.message : "it failed"}.</p>}
      {q.data && q.data.events === 0 && <p className="text-sm">The grid cites no record for this instance, so there is nothing to lay out.</p>}
      {q.data && q.data.lanes.map((lane) => (
        <div key={lane.person} className="mt-2">
          <h4 className="text-sm font-medium">{lane.label}</h4>
          <ol className="space-y-1 text-sm">
            {lane.events.map((e) => (
              <li key={e.ref} className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-xs" aria-label={`Event ${e.n}`}>{e.n}</span>
                <span className="text-xs text-muted-foreground">{when(e.at, e.day_only)}</span>
                <span className={`rounded px-1 text-xs ${KIND_CLASS[e.kind] ?? "bg-slate-100 text-slate-900"}`}>{e.kind_words}</span>
                <span>{e.text}{e.with.length > 0 ? ` (with ${e.with.join(", ")})` : ""}</span>
              </li>
            ))}
          </ol>
        </div>
      ))}
      {q.data && q.data.not_laid_out.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">{q.data.not_laid_out.length} cited record{q.data.not_laid_out.length === 1 ? "" : "s"} could not be read again and {q.data.not_laid_out.length === 1 ? "is" : "are"} not shown.</p>
      )}
    </section>
  )
}
