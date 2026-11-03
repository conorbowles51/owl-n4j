import { Link, useParams } from "react-router-dom"

/**
 * The phone analyses of a case (05). Each opens in the shared results layout. An approach whose measured gate failed
 * is listed with what was measured, so its absence is stated rather than silent.
 */
export const ANALYSES = [
  { path: "phone-money", title: "Money on the phones", what: "Bank and payment alerts and amounts on the phones, checked against the financial records." },
  { path: "phone-analyses/deletions", title: "Deleted and hidden", what: "What was deleted or made unreadable, when it can be placed, and conversations that lost more than the rest." },
  { path: "phone-analyses/relationships", title: "Relationships over time", what: "For each person on each phone: when contact began and ended, how each phone names them, and where contact rose or fell." },
  { path: "phone-analyses/groups", title: "Group admins and membership", what: "Admins of each group chat at extraction and the membership changes the phones record." },
]

export const NOT_BUILT = [
  { title: "Where two phones were together", why: "Not built: no two phones in the measured cases were placed in the same quarter hour often enough (43 times at most, 200 needed)." },
  { title: "Plans and check-ins against location", why: "Not built: the measured phones hold 3 calendar entries with a place (20 needed)." },
]

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
