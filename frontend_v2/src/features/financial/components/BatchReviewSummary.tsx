import { z } from "zod"
import { batchReviewSummarySchema } from "../lib/batch-review-summary"
import { Button } from "@/components/ui/button"
import { useState, type ReactNode } from "react"

export function BatchReviewSummary({
  summary,
  selected,
  onSelect,
  renderGroupAction,
}: {
  summary: z.infer<typeof batchReviewSummarySchema>
  selected: string
  onSelect: (group: string) => void
  renderGroupAction?: (group: string, count: number) => ReactNode
}) {
  const [showRetained, setShowRetained] = useState(false)
  const groups = summary.groups.filter(group => showRetained || group.blocked_statements > 0)
  return (
    <section
      aria-label="Review checks by reason"
      className="rounded border bg-card p-4 space-y-3"
    >
      <h3 className="font-semibold">Decisions needed before import</h3>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        {summary.blocked_statements ? (
          <Button
            variant="outline"
            size="sm"
            aria-pressed={selected === "blocked"}
            onClick={() => onSelect("blocked")}
          >
            {summary.blocked_statements} cannot be imported yet
          </Button>
        ) : (
          <p>No prepared statements are blocked from import.</p>
        )}
        {!!summary.importable_with_checks && (
          <p>
            {summary.importable_with_checks} can be imported with checks
            retained.
          </p>
        )}
        {!!summary.imported_with_checks && (
          <p>
            {summary.imported_with_checks} already imported with check history retained.
          </p>
        )}
      </div>
      {!!summary.groups.length && (
        <>
          <p className="text-xs text-muted-foreground">
            Current blockers appear first. Ready and saved statements keep their check history without becoming new import tasks. A statement can appear under more than one reason.
          </p>
          <ul className="divide-y max-h-72 overflow-y-auto pr-2">
            {groups.map((group) => (
              <li
                key={group.id}
                className="py-3 first:pt-0 last:pb-0 flex flex-wrap items-start justify-between gap-3"
              >
                <div className="min-w-0 flex-1 basis-72">
                  <p className="text-sm font-medium">
                    {group.label}{" "}
                    <span className="font-normal text-muted-foreground">
                      · {group.statement_count}{" "}
                      {group.statement_count === 1 ? "statement" : "statements"}
                    </span>
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {group.explanation}
                  </p>
                  <p className="text-xs mt-1">
                    {[
                      group.blocked_statements
                        ? `${group.blocked_statements} cannot be imported yet`
                        : "",
                      group.importable_statements
                        ? `${group.importable_statements} available to import`
                        : "",
                      group.imported_statements
                        ? `${group.imported_statements} already imported`
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                {!!group.blocked_statements && renderGroupAction?.(group.id, group.blocked_statements)}
                <Button
                  size="sm"
                  variant="outline"
                  aria-pressed={selected === group.id}
                  aria-label={`Show statements: ${group.label}`}
                  onClick={() => onSelect(group.id)}
                >
                  Show statements
                </Button>
                </div>
              </li>
            ))}
          </ul>
          {summary.groups.some(group => !group.blocked_statements) && (
            <Button variant="ghost" size="sm" onClick={() => setShowRetained(!showRetained)}>
              {showRetained ? "Hide retained check history" : "Show retained check history"}
            </Button>
          )}
        </>
      )}
      {!!summary.unchecked_balance_statements && (
        <details className="text-sm text-muted-foreground">
          <summary className="cursor-pointer">
            Automatic balance comparison unavailable for{" "}
            {summary.unchecked_balance_statements}{" "}
            {summary.unchecked_balance_statements === 1
              ? "statement"
              : "statements"}
          </summary>
          <p className="mt-1">
            A comparison needs readable opening and closing balances and payment
            values. Missing inputs mean the comparison could not run; they do
            not establish a difference. Any identified missing payment values
            are listed separately above.
          </p>
        </details>
      )}
    </section>
  )
}
