import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
import { statementCoverage } from "../lib/statement-coverage"
import { coverageMonths } from "../lib/coverage-months"

const displayMonth = (month: string) =>
  new Date(`${month}-01T00:00:00Z`).toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  })
const displayDate = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  })

export function OverviewStatementCoverage({
  caseId,
  active,
}: {
  caseId: string
  active: boolean
}) {
  const [offset, setOffset] = useState(0)
  const navigate = useNavigate()
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "coverage", undefined, offset],
    enabled: active,
    retry: false,
    queryFn: async () => {
      const data = statementCoverage.parse(
        await fetchAPI(
          `${candidateUrl("statement-coverage", caseId)}&offset=${offset}`
        )
      )
      assertCandidateScope(data, caseId)
      if (data.offset !== offset)
        throw Error("The account list changed. Refresh this check.")
      return data
    },
  })
  return (
    <section
      className="rounded-xl border bg-card p-5 space-y-3"
      aria-label="Which months do we have?"
    >
      <h3 className="font-semibold">Which months do we have?</h3>
      <p className="text-sm text-muted-foreground">
        Based on saved statements, including months with no transactions. Checks
        run separately for each account and currency.
      </p>
      {query.isPending ? (
        <p role="status">Checking saved statement dates…</p>
      ) : query.isError ? (
        <p role="alert">
          Statement dates could not be checked.{" "}
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </p>
      ) : (
        <>
          {!query.data.items.length && (
            <p>
              No saved account dates to check yet. Save statements to build the
              timeline.
            </p>
          )}
          {query.data.items.map((account) => (
            <div
              className="border-t pt-3 space-y-2 text-sm"
              key={account.account_id}
            >
              <h4 className="font-medium break-words">{account.label}</h4>
              {(!account.available || !account.currencies.length) && (
                <p>
                  We cannot check this account yet. Review its statement dates.
                </p>
              )}
              {account.currencies.map((group) => {
                const coverage = coverageMonths(group.windows)
                if (!coverage)
                  return (
                    <p key={group.currency}>
                      {group.currency}: statement dates need checking.
                    </p>
                  )
                const missing = coverage.months.filter(
                  (month) => month.status === "missing"
                )
                const partial = coverage.months.filter(
                  (month) => month.status === "partial"
                )
                return (
                  <div key={group.currency}>
                    <p className="font-medium">
                      {group.currency} · {missing.length} of{" "}
                      {coverage.months.length} months missing
                      {partial.length
                        ? ` · ${partial.length} months have gaps`
                        : ""}
                    </p>
                    <p>
                      Range checked: {displayDate(coverage.start)} to{" "}
                      {displayDate(coverage.end)}.
                    </p>
                    {missing.length > 0 && (
                      <p>
                        Missing:{" "}
                        {missing
                          .map((month) => displayMonth(month.month))
                          .join(", ")}
                        .
                      </p>
                    )}
                    {partial.length > 0 && (
                      <p>
                        Some dates missing in:{" "}
                        {partial
                          .map((month) => displayMonth(month.month))
                          .join(", ")}
                        .
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Earlier and later months have not been checked. Files still waiting
            to be saved may fill these gaps. Use account review to check a
            specific date range.
          </p>
          {(offset > 0 || query.data.has_more) && (
            <div className="flex gap-2">
              <Button
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 25))}
              >
                Previous accounts
              </Button>
              <Button
                disabled={!query.data.has_more}
                onClick={() => setOffset(offset + query.data.items.length)}
              >
                More accounts
              </Button>
            </div>
          )}
        </>
      )}
      <Button
        variant="outline"
        onClick={() =>
          navigate(`/cases/${caseId}/financial?view=statements&accounts=1`)
        }
      >
        Check dates and missing statements
      </Button>
    </section>
  )
}
