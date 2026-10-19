import { Button } from "@/components/ui/button"
import type { z } from "zod"
import type { statementBlocker } from "../lib/statement-assessment"

type Blocker = z.infer<typeof statementBlocker>
const fieldNames: Record<string, string> = {
  review: "Source reading",
  date: "Transaction date",
  description: "Description",
  counterparty: "Paid by / paid to",
  amount: "Payment amount",
  amount_minor: "Payment amount",
  direction: "Credit or debit",
  balance: "Printed balance",
  balance_minor: "Printed balance",
  source_order_anchor: "Printed position",
}

export function StatementRowReviewStatus({
  rowId,
  originalIssues,
  blockers,
  localProblems,
  pending,
  error,
  assessed,
  reviewed,
  excluded = false,
  saved,
  saving,
  failed,
  canMarkChecked,
  onMarkChecked,
  onInspect,
}: {
  rowId: string
  originalIssues: string[]
  blockers: Blocker[]
  localProblems: string[]
  pending: boolean
  error?: string
  assessed: boolean
  reviewed: boolean
  excluded?: boolean
  saved: boolean
  saving: boolean
  failed: boolean
  canMarkChecked: boolean
  onMarkChecked: () => void
  onInspect: (blocker: Blocker) => void
}) {
  const sourceResolved =
    assessed &&
    !pending &&
    !error &&
    reviewed &&
    !excluded &&
    !blockers.some((blocker) => blocker.kind === "reading")
  return (
    <section
      aria-label={`Row review ${rowId}`}
      className="w-full rounded border bg-background p-3 text-sm space-y-2"
    >
      {originalIssues.length > 0 && (
        <div>
          <p className="font-medium">Original extraction warning</p>
          <ul className="list-disc pl-5">
            {originalIssues.map((message, index) => (
              <li key={index}>{message}</li>
            ))}
          </ul>
        </div>
      )}
      <div aria-live="polite" className="space-y-1">
        <p className="font-medium">Current row checks</p>
        {pending ? (
          <p>Checking the current row values…</p>
        ) : error ? (
          <p>
            Current checks could not finish. {error} The original warning has
            not been confirmed as resolved.
          </p>
        ) : !assessed ? (
          <p>Current row assessment is unavailable.</p>
        ) : (
          <>
            {excluded && (
              <p>
                This row is excluded from import. Its original warning is
                retained; exclusion does not verify the source values.
              </p>
            )}
            {sourceResolved && (
              <p>
                The original extraction warning is resolved in the current
                review.
              </p>
            )}
            {blockers.length > 0 && (
              <ul className="space-y-2">
                {blockers.map((blocker, index) => {
                  const label =
                    fieldNames[blocker.target?.field || blocker.field || ""] ||
                    (blocker.kind === "reading"
                      ? "Source reading"
                      : "Row check")
                  return (
                    <li key={`${blocker.message}:${index}`}>
                      <p>
                        <span className="font-medium">{label}:</span>{" "}
                        {blocker.message}
                      </p>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onInspect(blocker)}
                      >
                        {label === "Source reading"
                          ? "Review source reading"
                          : `Review ${label.toLowerCase()}`}
                      </Button>
                    </li>
                  )
                })}
              </ul>
            )}
            {!excluded && !blockers.length && !localProblems.length && (
              <p>
                No current row check is outstanding. Statement reconciliation is
                checked separately.
              </p>
            )}
          </>
        )}
        {localProblems.length > 0 && (
          <ul className="list-disc pl-5">
            {localProblems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
      </div>
      {canMarkChecked && (
        <div className="space-y-1">
          <p>
            Compare the date, credit or debit, amount and balance with the
            original. If they are correct, record that check without changing
            the values.
          </p>
          <Button
            size="sm"
            variant="outline"
            disabled={pending || !!error || !assessed || saving}
            onClick={onMarkChecked}
          >
            Mark checked against original
          </Button>
        </div>
      )}
      {reviewed && (
        <p className="text-muted-foreground">
          {saving
            ? "Saving review progress…"
            : failed
              ? "Save not confirmed. Keep this review and retry Save progress."
              : saved
                ? "Row review saved to the case."
                : "This row review is not yet saved to the case. Use Save progress."}
        </p>
      )}
    </section>
  )
}
