import { useState } from "react"
import { useCaseworkEntries } from "@/features/workspace/hooks/use-casework"
import { Button } from "@/components/ui/button"
import { SavedFinancialReport } from "./SavedFinancialReport"

export function FinancialReportsList({ caseId }: { caseId: string }) {
  const [page, setPage] = useState(0)
  const query = useCaseworkEntries(caseId, {
    tag: "financial-report",
    limit: 25,
    offset: page * 25,
  })
  const reports =
    query.data?.entries.filter(
      (entry) =>
        entry.case_id === caseId && entry.tags.includes("financial-report")
    ) ?? []
  return (
    <section
      aria-label="Saved financial reports"
      className="space-y-3 rounded border bg-card p-4"
    >
      <h2 className="font-semibold">Financial reports</h2>
      <p className="text-sm">
        Reports assembled from selected financial findings, with the note
        versions and supporting records retained.
      </p>
      <a
        className="inline-block underline"
        href={`/cases/${caseId}/financial?view=findings`}
      >
        Create a report from financial findings
      </a>
      {query.isPending && <p role="status">Loading financial reports…</p>}
      {query.isError && (
        <p role="alert">
          Financial reports could not be loaded. {query.error.message}
        </p>
      )}
      {!query.isPending && !query.isError && !reports.length && (
        <p>No saved financial reports on this page.</p>
      )}
      {reports.map((entry) => (
        <article key={entry.id} className="space-y-2 border-t pt-3">
          <h3 className="font-medium">{entry.title || "Financial report"}</h3>
          <p className="text-sm">
            {entry.author_name || entry.author_email || "Author not recorded"}
            {entry.created_at
              ? ` · ${new Date(entry.created_at).toLocaleString()}`
              : ""}
          </p>
          <SavedFinancialReport
            key={entry.id + ":" + entry.version}
            caseId={caseId}
            entry={entry}
          />
        </article>
      ))}
      {(query.data?.total ?? 0) > 25 && (
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={page === 0 || query.isPlaceholderData}
            onClick={() => setPage((value) => value - 1)}
          >
            Previous financial reports
          </Button>
          <Button
            variant="outline"
            disabled={
              (page + 1) * 25 >= (query.data?.total ?? 0) ||
              query.isPlaceholderData
            }
            onClick={() => setPage((value) => value + 1)}
          >
            Next financial reports
          </Button>
        </div>
      )}
    </section>
  )
}
