import type { BatchStatementSummary } from "../lib/batch-statement-summary"

export function BatchProgressSummary({
  files,
  summary,
  available,
  imported,
  blocked,
  pending,
  skipped,
  duplicates,
  assigned,
}: {
  files: { status: string }[]
  summary?: BatchStatementSummary
  available: number
  imported: number
  blocked?: number
  pending: number
  skipped: number
  duplicates: number
  assigned: number
}) {
  const states: [string, number | undefined][] = [
    ["Ready to save", summary?.available ?? available],
    ["Needs review before saving", summary?.blocked ?? blocked],
    ["Saved to Financial", summary?.imported ?? imported],
    ["Save in progress", summary?.pending_import ?? pending],
    ["Left unimported", summary?.skipped ?? skipped],
    ["Duplicate copies ignored", summary?.duplicate_ignored ?? duplicates],
    ["Assignments completed", summary?.assigned ?? assigned],
    ["Other reviews", summary?.other],
  ]
  const read = files.filter((file) => file.status === "checked").length
  const failed = files.filter((file) => file.status === "error").length
  return (
    <section
      aria-label="Batch progress"
      className="space-y-3 rounded border bg-card p-4"
    >
      <div>
        <h3 className="font-semibold">PDF files</h3>
        <p>
          {read} of {files.length} files read
          {failed ? ` · ${failed} need a reading check` : ""}
        </p>
        <p className="text-sm text-muted-foreground">
          One PDF can contain several accounts or statement periods. Reading
          prepares reviews; saving is a separate step.
        </p>
      </div>
      <div>
        <h3 className="font-semibold">
          {summary
            ? `${summary.total} prepared statement reviews`
            : "Prepared statement reviews"}
        </h3>
        <p className="text-sm text-muted-foreground">
          These are reviews, not PDF counts. They can include pages still
          waiting for an account or period to be identified.
        </p>
      </div>
      <dl className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {states
          .filter(([, count], index) => index < 3 || !!count)
          .map(([label, count]) => (
            <div
              key={label}
              className={`rounded border p-3 ${label === "Needs review before saving" && count ? "border-amber-400 bg-amber-50/60 dark:bg-amber-950/20" : "bg-background"}`}
            >
              <dt className="text-sm text-muted-foreground">{label}</dt>
              <dd className="text-2xl font-semibold">
                {count ?? "Not available"}
              </dd>
            </div>
          ))}
      </dl>
      <p className="text-xs text-muted-foreground">
        {summary
          ? "Each prepared review appears in one status above. "
          : "Status counts cover the whole batch. "}
        Review reasons below may overlap these statuses and each other; do not
        add reason counts to the status counts.
      </p>
    </section>
  )
}
