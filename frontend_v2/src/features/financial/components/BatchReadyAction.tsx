import { Button } from "@/components/ui/button"
import type { BatchStatementSummary } from "../lib/batch-statement-summary"

export function BatchReadyAction({
  available,
  payments,
  incomplete,
  summary,
  filtered,
  canEdit,
  paused,
  pending,
  accepted,
  onConfirm,
}: {
  available: number
  payments: number
  incomplete: number
  summary?: BatchStatementSummary
  filtered: boolean
  canEdit: boolean
  paused: boolean
  pending: boolean
  accepted: boolean
  onConfirm: () => void
}) {
  const statements = `${available} ${available === 1 ? "statement" : "statements"}`
  const noPayments = payments === 0 && incomplete === 0
  const confirmedQuiet =
    available > 0 && summary?.available_no_activity === available
  return (
    <section
      aria-label="Save ready statements"
      className="rounded border border-primary/50 bg-card p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1 basis-64">
          <h3 className="font-semibold">
            {available} prepared {available === 1 ? "review" : "reviews"} ready
            · {payments} transactions to import
            {incomplete ? ` · ${incomplete} incomplete records` : ""}
          </h3>
          {available > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              {confirmedQuiet
                ? "These statements are confirmed to contain no payments. Save their account details, dates and balances to Financial. Find them in Accounts; no transaction rows will be added."
                : noPayments
                  ? "These ready reviews contain no payments to import. Save their statement details to Financial and find them in Accounts. A zero payment count alone does not confirm no activity; open a review if you expected transactions."
                  : "Save the statements’ account details, dates and balances to Financial and add their payments to Transactions."}
            </p>
          )}
        </div>
        <Button
          className="h-auto whitespace-normal py-2"
          disabled={!canEdit || !available || pending || paused}
          onClick={onConfirm}
        >
          {pending
            ? "Submitting save request…"
            : !available
              ? "No statements ready to save"
              : noPayments
                ? `Save ${statements} to Financial`
                : incomplete
                  ? `Import ${payments} transactions and ${incomplete} incomplete records`
                  : summary && summary.available_with_payments < available
                    ? `Import ${payments} transactions and save ${statements}`
                    : `Import ${payments} transactions`}
        </Button>
      </div>
      {!!summary?.available_no_activity && !confirmedQuiet && (
        <p className="text-sm">
          {summary.available_no_activity} ready{" "}
          {summary.available_no_activity === 1
            ? "statement is"
            : "statements are"}{" "}
          confirmed to contain no payments; their account details, dates and
          balances will also be saved.
        </p>
      )}
      {!!incomplete && (
        <p className="text-sm">
          Incomplete records will be saved separately for review and kept
          outside totals.
        </p>
      )}
      {filtered && (
        <p className="text-sm">
          This action covers all ready statements in the batch, including
          statements outside the review filter.
        </p>
      )}
      {paused && (
        <p className="text-sm">
          Resume batch preparation before saving ready statements.
        </p>
      )}
      {!canEdit && (
        <p className="text-sm">
          You can review this batch. Saving statements requires edit access.
        </p>
      )}
      {pending && (
        <p role="status" className="text-sm">
          Submitting the ready statements. Keep this request open until a result
          is shown.
        </p>
      )}
      {accepted && !pending && (
        <p role="status" className="text-sm">
          Request accepted. Import results below show which statements are
          saved, still processing or need review.
        </p>
      )}
    </section>
  )
}
