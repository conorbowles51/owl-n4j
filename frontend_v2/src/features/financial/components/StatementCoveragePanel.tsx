import { StatementTimeline } from "./StatementTimeline"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
const day = z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/)
const count = z.number().int().nonnegative()
const report = z.object({
  case_id: z.string(),
  offset: count,
  has_more: z.boolean(),
  applied: z.literal(false),
  limitation: z.string(),
  items: z.array(
    z.object({
      account_id: z.string(),
      label: z.string(),
      available: z.boolean(),
      reason: z.string().nullable(),
      periods: z.array(
        z.object({
          period_id: z.string(),
          source_document_id: z.string(),
          evidence_file_id: z.string().nullable(),
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
          period_count: count,
          covered_days: count,
          uncovered_days: count,
          windows: z.array(
            z.object({ start: day, end: day, period_ids: z.array(z.string()) })
          ),
          gaps: z.array(z.object({ start: day, end: day, days: count })),
          overlaps: z.array(
            z.object({ period_id: z.string(), start: day, end: day })
          ),
        })
      ),
    })
  ),
})
const reasons = {
  source_not_admitted: "Source excluded from the current ledger",
  missing_dates: "Statement dates missing",
  dates_not_printed: "Dates derived rather than printed",
  invalid_date_range: "End date is before start date",
}
export function StatementCoveragePanel({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [opened, setOpened] = useState(false),
    [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "coverage", offset],
    enabled: opened && Boolean(caseId),
    retry: false,
    queryFn: async () => {
      const data = report.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("statement-coverage", caseId!)}&offset=${offset}`
        )
      )
      assertCandidateScope(data, caseId!)
      if (data.offset !== offset)
        throw new Error("The account page changed. Reload coverage.")
      return data
    },
  })
  if (!caseId) return <p>Choose a case to check statement coverage.</p>
  return (
    <section
      className="space-y-3 rounded border p-4"
      aria-label="Statement coverage"
    >
      <h3 className="font-semibold">Statement coverage</h3>
      <p>
        Check which dates are covered by recorded, printed statement bounds.
        This does not establish that all transactions were extracted.
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh statement coverage" : "Check statement coverage"}
      </Button>
      {opened &&
        (query.isPending ? (
          <p role="status">Checking statement dates…</p>
        ) : query.isError ? (
          <p role="alert">Coverage unavailable. {query.error.message}</p>
        ) : (
          <>
            <p>{query.data.limitation}</p>
            {query.data.items.length === 0 && (
              <p>
                No ledger accounts on this page. This does not establish that
                the case has no financial records.
              </p>
            )}
            {query.data.items.map((account) => (
              <div
                key={account.account_id}
                className="space-y-2 rounded border p-3"
              >
                <h4 className="font-semibold">{account.label}</h4>
                {!account.available ? (
                  <p>{account.reason}</p>
                ) : (
                  <>
                    {account.currencies.length === 0 && (
                      <p>
                        No eligible printed date ranges. Coverage is unknown.
                      </p>
                    )}
                    {account.currencies.map((group) => (
                      <div key={group.currency} className="space-y-1">
                        <p>
                          {group.currency}: {group.period_count} eligible
                          periods; {group.covered_days} calendar days within
                          their combined bounds.
                        </p>
                        {group.windows.map((window) => (
                          <p key={window.start}>
                            Covered bounds: {window.start} to {window.end} (
                            {window.period_ids.length} source periods).
                          </p>
                        ))}
                        {group.gaps.map((gap) => (
                          <p key={gap.start}>
                            Gap in eligible printed bounds: {gap.start} to{" "}
                            {gap.end} ({gap.days} days).
                          </p>
                        ))}
                        {group.gaps.length === 0 && (
                          <p>
                            No internal gaps between eligible printed bounds.
                            Earlier and later records remain unassessed.
                          </p>
                        )}
                        <p>
                          {group.overlaps.length} additional periods overlap
                          already covered dates; overlapping days are counted
                          once.
                        </p>
                      </div>
                    ))}
                    {[
                      ...new Set(
                        account.periods.map((period) => period.currency)
                      ),
                    ]
                      .sort()
                      .map((currency) => (
                        <StatementTimeline
                          key={currency}
                          caseId={caseId}
                          currency={currency}
                          periods={account.periods}
                          gaps={
                            account.currencies.find(
                              (group) => group.currency === currency
                            )?.gaps ?? []
                          }
                          overlaps={
                            account.currencies.find(
                              (group) => group.currency === currency
                            )?.overlaps ?? []
                          }
                        />
                      ))}
                    <details>
                      <summary>
                        Source periods ({account.periods.length})
                      </summary>
                      {account.periods.map((period) => (
                        <p key={period.period_id}>
                          {period.start ?? "Unknown start"} to{" "}
                          {period.end ?? "unknown end"} · {period.currency} ·{" "}
                          {period.included
                            ? "Included printed bounds"
                            : reasons[period.exclusion_reason!]}{" "}
                          · source document {period.source_document_id}
                        </p>
                      ))}
                    </details>
                  </>
                )}
              </div>
            ))}
            <div className="flex gap-2">
              <Button
                disabled={!offset || query.isFetching}
                onClick={() => setOffset((v) => Math.max(0, v - 25))}
              >
                Previous coverage accounts
              </Button>
              <Button
                disabled={!query.data.has_more || query.isFetching}
                onClick={() => setOffset((v) => v + 25)}
              >
                Next coverage accounts
              </Button>
            </div>
          </>
        ))}
    </section>
  )
}
