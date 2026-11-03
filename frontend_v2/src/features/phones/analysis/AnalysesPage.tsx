import { Link, useParams } from "react-router-dom"
import { ANALYSES, NOT_BUILT } from "./analyses-list"

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
      <section aria-label="Not built" className="space-y-1 text-xs text-muted-foreground">
        <h2 className="text-sm font-medium text-foreground">Not offered, and why</h2>
        <ul className="list-disc pl-4">{NOT_BUILT.map((n) => <li key={n.title}>{n.title}: {n.why}</li>)}</ul>
      </section>
    </div>
  )
}
