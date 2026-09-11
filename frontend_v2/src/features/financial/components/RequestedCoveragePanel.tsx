import { StatementSourceButton } from "./StatementSourceButton"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const count = z.number().int().nonnegative()
const report = z.object({
  case_id: z.string(),
  account_id: z.string(),
  start_date: day,
  end_date: day,
  requested_days: count.positive(),
  available: z.boolean(),
  reason: z.string().nullable(),
  applied: z.literal(false),
  limitation: z.string(),
  periods: z.array(
    z.object({
      period_id: z.string(),
      source_document_id: z.string(),
      currency: z.string(),
      start: day.nullable(),
      end: day.nullable(),
      included: z.boolean(),
      exclusion_reason: z
        .enum([
          "source_not_admitted",
          "missing_dates",
          "dates_not_printed",
          "invalid_date_range",
        ])
        .nullable(),
    })
  ),
  currencies: z.array(
    z.object({
      currency: z.string(),
      covered_days: count,
      uncovered_days: count,
      windows: z.array(
        z.object({ start: day, end: day, period_ids: z.array(z.string()) })
      ),
      gaps: z.array(z.object({ start: day, end: day, days: count.positive() })),
    })
  ),
})
const reasons = {
  source_not_admitted: "Source excluded from the current ledger",
  missing_dates: "Statement dates missing",
  dates_not_printed: "Dates derived rather than printed",
  invalid_date_range: "End date precedes start date",
}
export function RequestedCoveragePanel({
  caseId,
  params,
  accountLabel,
  autoLoad = false,
}: {
  caseId: string
  params: LedgerQueryParams
  accountLabel?: string
  autoLoad?: boolean
}) {
  if (!params.accountId || !params.startDate || !params.endDate)
    return (
      <p className="text-sm text-muted-foreground">
        Choose one account and enter a start and end date to check for missing
        statements.
      </p>
    )
  return (
    <CoverageResult
      key={JSON.stringify([
        caseId,
        params.accountId,
        params.startDate,
        params.endDate,
      ])}
      caseId={caseId}
      accountId={params.accountId}
      start={params.startDate}
      end={params.endDate}
      accountLabel={accountLabel}
      autoLoad={autoLoad}
    />
  )
}
function CoverageResult({
  caseId,
  accountId,
  start,
  end,
  accountLabel,
  autoLoad,
}: {
  caseId: string
  accountId: string
  start: string
  end: string
  accountLabel?: string
  autoLoad: boolean
}) {
  const [opened, setOpened] = useState(autoLoad)
  const query = useQuery({
    queryKey: [
      "financial-ledger",
      caseId,
      "requested-coverage",
      accountId,
      start,
      end,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const data = report.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("requested-statement-coverage", caseId)}&${new URLSearchParams({ account_id: accountId, start_date: start, end_date: end })}`
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.account_id !== accountId ||
        data.start_date !== start ||
        data.end_date !== end
      )
        throw new Error(
          "Coverage returned for different filters. Reload the check."
        )
      if (
        data.currencies.some(
          (group) =>
            group.covered_days + group.uncovered_days !== data.requested_days
        )
      )
        throw new Error("Coverage day counts disagree. Reload the check.")
      return data
    },
  })
  return (
    <section
      aria-label="Requested statement dates"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">Requested statement dates</h3>
      <p>
        {start} to {end}
        {accountLabel ? ` · ${accountLabel}` : ""}
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh date check" : "Check these dates"}
      </Button>
      {opened &&
        (query.isFetching || query.isPending ? (
          <p role="status">Checking requested dates…</p>
        ) : query.isError ? (
          <p role="alert">Coverage unavailable. {query.error.message}</p>
        ) : (
          <>
            <p className="text-sm">
              This checks statement dates, not whether every payment was
              extracted correctly.
            </p>
            {!query.data.available ? (
              <p>
                Statement coverage could not be established. {query.data.reason}
              </p>
            ) : (
              query.data.currencies.map((group) => (
                <div key={group.currency} className="space-y-1">
                  <p>
                    {group.currency}: {group.covered_days} of{" "}
                    {query.data.requested_days} days covered by statements;{" "}
                    {group.uncovered_days} days without a covering statement.
                  </p>
                  {group.gaps.map((gap) => (
                    <p key={gap.start}>
                      Missing statement dates: {gap.start} to {gap.end} (
                      {gap.days} days).
                    </p>
                  ))}
                  {group.uncovered_days === 0 && (
                    <p>
                      Statements cover the full date range. Check their balance
                      results separately to look for missing or incorrect
                      payments.
                    </p>
                  )}
                  {group.windows.map((window) => (
                    <p key={window.start}>
                      Statements cover: {window.start} to {window.end}
                    </p>
                  ))}
                </div>
              ))
            )}
            <details>
              <summary>
                Open the statements used in this check (
                {query.data.periods.length})
              </summary>
              {query.data.periods.map((period) => (
                <div key={period.period_id} className="space-y-2 border-t py-2">
                  <p>
                    {period.start ?? "Unknown start"} to{" "}
                    {period.end ?? "unknown end"} · {period.currency} ·{" "}
                    {period.included
                      ? "Dates available; only days in your requested range count"
                      : reasons[period.exclusion_reason!]}
                  </p>
                  <StatementSourceButton
                    caseId={caseId}
                    periodId={period.period_id}
                    sourceDocumentId={period.source_document_id}
                    label="Open statement and dates"
                  />
                </div>
              ))}
            </details>
            <details className="text-sm">
              <summary className="cursor-pointer">
                How dates are checked
              </summary>
              <p>{query.data.limitation}</p>
            </details>
          </>
        ))}
    </section>
  )
}
