import { StatementSourceButton } from "./StatementSourceButton"
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
  account_id: z.string().nullable().optional(),
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
  autoLoad = false,
  accountId,
}: {
  caseId: string | undefined
  autoLoad?: boolean
  accountId?: string
}) {
  const [opened, setOpened] = useState(autoLoad),
    [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "coverage", accountId, offset],
    enabled: opened && Boolean(caseId),
    retry: false,
    queryFn: async () => {
      const data = report.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("statement-coverage", caseId!)}&offset=${offset}${accountId ? `&account_id=${encodeURIComponent(accountId)}` : ""}`
        )
      )
      assertCandidateScope(data, caseId!)
      if (
        accountId &&
        (data.account_id !== accountId ||
          data.items.some((account) => account.account_id !== accountId))
      )
        throw new Error(
          "Coverage returned for a different account. Reload the check."
        )
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
        See the dates covered by imported statements and any gaps between them.{" "}
        {accountId
          ? "Use the date range check below to include earlier or later dates."
          : "Review an individual account to check an earlier or later date range."}
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
            <details className="text-sm">
              <summary className="cursor-pointer">
                How dates are checked
              </summary>
              <p>{query.data.limitation}</p>
            </details>
            {query.data.items.length === 0 && (
              <p>No accounts were found on this page.</p>
            )}
            {query.data.items.map((account) => (
              <div
                key={account.account_id}
                className="space-y-2 rounded border p-3"
              >
                {!accountId && (
                  <h4 className="font-semibold">{account.label}</h4>
                )}
                {!account.available ? (
                  <p>{account.reason}</p>
                ) : (
                  <>
                    {account.currencies.length === 0 && (
                      <p>
                        Statement dates are missing or cannot be used. Open the
                        source statements to check their dates.
                      </p>
                    )}
                    {account.currencies.map((group) => (
                      <div key={group.currency} className="space-y-1">
                        <p>
                          {group.currency}: {group.period_count} statement{" "}
                          {group.period_count === 1
                            ? "period covers"
                            : "periods cover"}{" "}
                          {group.covered_days} days.
                        </p>
                        {group.windows.map((window) => (
                          <p key={window.start}>
                            Statements cover: {window.start} to {window.end} (
                            {window.period_ids.length}{" "}
                            {window.period_ids.length === 1
                              ? "statement"
                              : "statements"}
                            ).
                          </p>
                        ))}
                        {group.gaps.map((gap) => (
                          <p key={gap.start}>
                            Missing statement dates: {gap.start} to {gap.end} (
                            {gap.days} days).
                          </p>
                        ))}
                        {group.gaps.length === 0 && (
                          <p>
                            No gaps between these statements. Earlier and later
                            dates have not been checked.
                          </p>
                        )}
                        {group.overlaps.length > 0 && (
                          <p>
                            {group.overlaps.length} statement{" "}
                            {group.overlaps.length === 1
                              ? "period overlaps"
                              : "periods overlap"}{" "}
                            another statement. Check overlapping files for
                            duplicate or additional transactions.
                          </p>
                        )}
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
                        Statements included or left out (
                        {account.periods.length})
                      </summary>
                      {account.periods.map((period) => (
                        <div
                          key={period.period_id}
                          className="space-y-2 border-t py-2"
                        >
                          <p>
                            {period.start ?? "Unknown start"} to{" "}
                            {period.end ?? "unknown end"} · {period.currency} ·{" "}
                            {period.included
                              ? "Dates included"
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
                  </>
                )}
              </div>
            ))}
            {!accountId && (
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
            )}
          </>
        ))}
    </section>
  )
}
