import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { ReadyStatementPeriod } from "../hooks/use-statement-register"

/** Open the exact prepared period; importing remains an explicit review action. */
export function ReadyStatementPeriods({
  periods,
  onReview,
  canEdit,
}: {
  periods: ReadyStatementPeriod[]
  onReview: (statementId: string) => void
  canEdit: boolean
}) {
  const [page, setPage] = useState(0)
  const lastPage = Math.max(0, Math.ceil(periods.length / 5) - 1)
  const current = Math.min(page, lastPage)
  return (
    <div className="space-y-2">
      <ul
        className="divide-y rounded border"
        aria-label="Ready statement periods"
      >
        {periods.slice(current * 5, current * 5 + 5).map((period) => (
          <li
            key={period.statement_id}
            className="flex flex-wrap items-center justify-between gap-3 p-3"
          >
            <div className="min-w-0 space-y-1 text-sm">
              <p className="font-medium break-words">
                {[
                  period.holder,
                  period.institution,
                  period.account,
                  period.currency,
                ]
                  .filter(Boolean)
                  .join(" · ") || "Statement details need review"}
              </p>
              <p>
                {period.period_start || "Start not recorded"} to{" "}
                {period.period_end || "End not recorded"}
              </p>
              <p className="text-muted-foreground">
                {period.transaction_count
                  ? `${period.transaction_count} ${period.transaction_count === 1 ? "payment" : "payments"} ready to import`
                  : "Account and balances ready to save"}
                {period.incomplete_count > 0 &&
                  ` · ${period.incomplete_count} incomplete records`}
                {period.problem_count > 0 &&
                  ` · ${period.problem_count} ${period.problem_count === 1 ? "check" : "checks"} to review`}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => onReview(period.statement_id)}
            >
              {canEdit ? "Review and import" : "Review statement"}
            </Button>
          </li>
        ))}
      </ul>
      {periods.length > 5 && (
        <div className="flex items-center gap-2 text-sm">
          <Button
            variant="outline"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            Previous ready statements
          </Button>
          <span>
            Page {current + 1} of {lastPage + 1}
          </span>
          <Button
            variant="outline"
            disabled={current === lastPage}
            onClick={() => setPage(current + 1)}
          >
            Next ready statements
          </Button>
        </div>
      )}
    </div>
  )
}
