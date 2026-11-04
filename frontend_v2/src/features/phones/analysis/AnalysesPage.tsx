import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ANALYSES, NOT_BUILT } from "./analyses-list"
import { keptResults } from "./analysis-api"
import { recordsWords } from "./count-words"
import { SourceExport } from "./SourceExport"

/**
 * The phone analyses of a case (05). Each opens in the shared results layout. An approach whose measured gate failed
 * is listed with what was measured, so its absence is stated rather than silent.
 */

export default function AnalysesPage() {
  const { id: caseId = "" } = useParams()
  return (
    <div className="space-y-4 p-4" data-testid="phone-analyses-page">
      <h1 className="text-lg font-semibold">Phone analyses</h1>
      <p className="text-sm">Each analysis points to records to examine. Every result is a lead for enquiry, not a finding.</p>
      <ul className="space-y-2">
        {ANALYSES.map((a) => (
          <li key={a.path} className="rounded border p-2 text-sm">
            <Link className="font-medium underline" to={`/cases/${caseId}/${a.path}`}>{a.title}</Link>
            <p className="text-xs">{a.what}</p>
          </li>
        ))}
      </ul>
      <KeptList caseId={caseId} />
      {NOT_BUILT.length > 0 && <section aria-label="Not built" className="space-y-1 text-xs text-muted-foreground">
        <h2 className="text-sm font-medium text-foreground">Not offered, and why</h2>
        <ul className="list-disc pl-4">{NOT_BUILT.map((n) => <li key={n.title}>{n.title}: {n.why}</li>)}</ul>
      </section>}
    </div>
  )
}

/** Kept results (05 3.4): each opens in its analysis and exports the records it was kept with (07 J-14b). */
function KeptList({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["phone-analysis-kept-list", caseId], queryFn: () => keptResults(caseId), enabled: !!caseId })
  if (!q.data || q.data.total === 0) return null
  const shown = q.data.items.length
  return (
    <section aria-label="Kept results" className="space-y-2 text-sm">
      <h2 className="font-medium">Kept results</h2>
      <p className="text-xs">{q.data.total.toLocaleString("en-US")} kept{shown < q.data.total ? `, the latest ${shown.toLocaleString("en-US")} shown` : ""}.</p>
      <ul className="space-y-2">
        {q.data.items.map((k) => {
          const a = ANALYSES.find((x) => x.code === k.approach)
          return (
            <li key={k.id} className="rounded border p-2" data-testid="kept-result">
              {a ? <Link className="underline" to={`/cases/${caseId}/${a.path}?kept=${encodeURIComponent(k.id)}`}>{k.label}</Link> : <span>{k.label}</span>}
              <p className="text-xs">{recordsWords(k.record_count)} behind it{k.created_by_name ? `, kept by ${k.created_by_name}` : ""}.</p>
              {k.record_count > 0 && <SourceExport caseId={caseId} source="analysis_result" refBody={{ kept_id: k.id }} label="Export…" />}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
