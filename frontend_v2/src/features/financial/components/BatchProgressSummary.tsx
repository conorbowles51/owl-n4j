import type { BatchStatementSummary } from "../lib/batch-statement-summary"
import { Button } from "@/components/ui/button"

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
  onSelect,
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
  onSelect?: (group: string) => void
}) {
  const states: [string, number | undefined][] = [
    ["Ready to save", summary?.available ?? available],
    ["Needs review before saving", summary?.blocked ?? blocked],
    ["Saved to Financial", summary?.imported ?? imported],
    ["Save in progress", summary?.pending_import ?? pending],
    ["Left unimported", summary?.skipped ?? skipped],
    ["Possible duplicates", summary?.possible_duplicates],
    ["Duplicate copies ignored", summary?.duplicate_ignored ?? duplicates],
    ["Assignments completed", summary?.assigned ?? assigned],
    ["Other reviews", summary?.other],
  ]
  const read = files.filter((file) => file.status === "checked").length
  const failed = files.filter((file) => file.status === "error").length
  const unread = files.length - read
  return (
    <section
      aria-label="Batch progress"
      className="space-y-3 rounded border bg-card p-4"
    >
      {summary && (
        <div className="space-y-2" aria-label="Your batch progress">
          <h3 className="font-semibold">Your progress through this batch</h3>
          <p role="status">
            {summary.imported} saved to Financial ·{" "}
            {summary.available + summary.blocked} prepared reviews still to
            finish
            {unread > 0 && ` · ${unread} files still need reading`}
          </p>
          <ProgressBar
            parts={[
              ["Saved to Financial", summary.imported, "#2f9353"],
              ["Ready to save", summary.available, "#3a6fd8"],
              ["Need corrections or a decision", summary.blocked, "#c67a10"],
              ["Saves in progress", summary.pending_import, "#9bb8f0"],
              [
                "Left unimported or ignored",
                summary.skipped + summary.duplicate_ignored,
                "#8060a9",
              ],
              ["Assigned elsewhere", summary.assigned, "#8a8d96"],
            ]}
          />
          <p className="text-sm text-muted-foreground">
            {summary.available} ready to save · {summary.blocked} need
            corrections or a decision. {summary.pending_import} saves in
            progress. {summary.skipped + summary.duplicate_ignored} left
            unimported or ignored. {summary.assigned} assigned to another
            account or period.
            {summary.other > 0 &&
              ` ${summary.other} other reviews still require inspection.`}{" "}
            Saved statements can retain original extraction flags; those flags
            do not mean you must import them again.
          </p>
          {onSelect && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => onSelect("unfinished")}>
                Show unfinished statements
              </Button>
              <Button
                variant="outline"
                onClick={() => onSelect("ready_to_save")}
              >
                Show ready to save
              </Button>
              <Button variant="outline" onClick={() => onSelect("duplicates")}>
                Review duplicates (
                {(summary.possible_duplicates ?? 0) + summary.duplicate_ignored}
                )
              </Button>
              <Button variant="outline" onClick={() => onSelect("saved")}>
                Show already saved
              </Button>
            </div>
          )}
        </div>
      )}
      {unread > 0 && (
        <p role="status" className="rounded border border-amber-400 p-3">
          {failed > 0
            ? `${failed} files failed before statement review. Open File processing below for the error and recovery action.`
            : `${unread} files have not finished reading.`}{" "}
          Zero prepared reviews does not mean this batch is finished.
        </p>
      )}
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

/** One bar for the batch: each part's share, with a legend that carries every count as text. */
function ProgressBar({ parts }: { parts: [string, number, string][] }) {
  const shown = parts.filter(([, count]) => count > 0)
  const total = shown.reduce((sum, [, count]) => sum + count, 0)
  if (!total) return null
  return (
    <div className="space-y-1.5">
      <div
        aria-hidden="true"
        className="flex h-3 w-full gap-0.5 overflow-hidden rounded-sm"
      >
        {shown.map(([label, count, colour]) => (
          <span
            key={label}
            title={`${label}: ${count}`}
            style={{ flexGrow: count, background: colour }}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Batch progress by state">
        {shown.map(([label, count, colour]) => (
          <li key={label} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-sm"
              style={{ background: colour }}
            />
            {label}: {count}
          </li>
        ))}
      </ul>
    </div>
  )
}
