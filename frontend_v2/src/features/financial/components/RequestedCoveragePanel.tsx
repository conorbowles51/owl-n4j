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
}: {
  caseId: string
  params: LedgerQueryParams
}) {
  if (!params.accountId || !params.startDate || !params.endDate)
    return (
      <p className="text-sm text-muted-foreground">
        To check coverage for a search, apply one ledger account and both date
        bounds.
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
    />
  )
}
function CoverageResult({
  caseId,
  accountId,
  start,
  end,
}: {
  caseId: string
  accountId: string
  start: string
  end: string
}) {
  const [opened, setOpened] = useState(false)
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
      aria-label="Coverage for applied ledger filters"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">Coverage for applied ledger filters</h3>
      <p>
        {start} to {end} · account {accountId}
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh filtered coverage" : "Check filtered coverage"}
      </Button>
      {opened &&
        (query.isFetching || query.isPending ? (
          <p role="status">Checking requested dates…</p>
        ) : query.isError ? (
          <p role="alert">Coverage unavailable. {query.error.message}</p>
        ) : (
          <>
            <p>{query.data.limitation}</p>
            {!query.data.available ? (
              <p>Coverage unknown or unavailable. {query.data.reason}</p>
            ) : (
              query.data.currencies.map((group) => (
                <div key={group.currency} className="space-y-1">
                  <p>
                    {group.currency}: {group.covered_days} of{" "}
                    {query.data.requested_days} requested days within eligible
                    printed bounds; {group.uncovered_days} days uncovered.
                  </p>
                  {group.gaps.map((gap) => (
                    <p key={gap.start}>
                      Uncovered requested dates: {gap.start} to {gap.end} (
                      {gap.days} days).
                    </p>
                  ))}
                  {group.uncovered_days === 0 && (
                    <p>
                      Printed bounds cover these requested dates. This does not
                      establish complete transaction extraction or that no
                      transactions occurred.
                    </p>
                  )}
                  {group.windows.map((window) => (
                    <p key={window.start}>
                      Covered requested dates: {window.start} to {window.end} ·
                      source periods {window.period_ids.join(", ")}
                    </p>
                  ))}
                </div>
              ))
            )}
            <details>
              <summary>
                Recorded source periods ({query.data.periods.length})
              </summary>
              {query.data.periods.map((period) => (
                <p key={period.period_id}>
                  {period.start ?? "Unknown start"} to{" "}
                  {period.end ?? "unknown end"} · {period.currency} ·{" "}
                  {period.included
                    ? "Eligible printed bounds; only intersecting dates count"
                    : reasons[period.exclusion_reason!]}
                  {" · "}period {period.period_id} · source document{" "}
                  {period.source_document_id}
                </p>
              ))}
            </details>
          </>
        ))}
    </section>
  )
}
