import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
import { statementCoverage } from "../lib/statement-coverage"
import { coverageMonths } from "../lib/coverage-months"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Disclosure } from "./Disclosure"
import { InfoTip } from "./InfoTip"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"
import { StatementSourceButton } from "./StatementSourceButton"
import type { StatementCoverageAccount } from "../lib/statement-coverage"

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

const monthEnd = (month: string) => {
  const day = new Date(`${month}-01T00:00:00Z`)
  day.setUTCMonth(day.getUTCMonth() + 1)
  day.setUTCDate(0)
  return day.toISOString().slice(0, 10)
}

type OpenedMonth = {
  account: StatementCoverageAccount
  label: string
  currency: string
  month: string
  status: "covered" | "partial" | "missing"
}

/** Saved statements of this account and currency whose dates reach into the month. */
const periodsInMonth = (opened: Omit<OpenedMonth, "label" | "status">) =>
  opened.account.periods.filter(
    (period) =>
      period.included &&
      period.currency === opened.currency &&
      !!period.start &&
      !!period.end &&
      period.start <= monthEnd(opened.month) &&
      period.end >= `${opened.month}-01`
  )

export function OverviewStatementCoverage({
  caseId,
  active,
}: {
  caseId: string
  active: boolean
}) {
  const [offset, setOffset] = useState(0)
  const [opened, setOpened] = useState<OpenedMonth | null>(null)
  const navigate = useNavigate()
  const reviewFile = (fileId: string) =>
    navigate(
      `/cases/${caseId}/financial?view=statements&files=1&reviewFile=${encodeURIComponent(fileId)}`
    )
  // A month with one statement opens it; several, or a missing month, open a short list or the dates check.
  const openMonth = (month: OpenedMonth) => {
    const periods = month.status === "missing" ? [] : periodsInMonth(month)
    if (periods.length === 1 && periods[0].evidence_file_id)
      reviewFile(periods[0].evidence_file_id)
    else setOpened(month)
  }
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
  const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.02em" }
  const cell = (status: string) =>
    status === "covered"
      ? { background: "#2f9353" }
      : status === "partial"
        ? { background: "repeating-linear-gradient(135deg,#f2c46b 0 4px,#fdf0d5 4px 8px)" }
        : { background: "#fdf0d5", border: "1.5px dashed #d99a2b" }
  return (
    <section
      className="space-y-4 rounded-[14px] bg-card p-5 sm:p-6"
      style={{ boxShadow: "0 1px 0 #e4e3df, 0 8px 24px rgba(20,22,27,.05)" }}
      aria-label="Which months do we have?"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-[22px] font-semibold" style={heading}>
          Do we have every statement?
          <InfoTip text="Which months do we have? Based on saved statements, including months with no transactions. Checks run separately for each account and currency." />
        </h3>
        <div className="flex flex-wrap items-center gap-4 text-[13px]">
          <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="size-3 rounded-[3px]" style={cell("covered")} />Have it</span>
          <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="size-3 rounded-[3px]" style={cell("partial")} />Some dates missing</span>
          <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="size-3 rounded-[3px]" style={cell("missing")} />Missing from the case</span>
        </div>
      </div>
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
          <ul className="divide-y">
          {query.data.items.map((account) => (
            <li
              className="grid gap-x-5 gap-y-2 py-3 text-sm md:grid-cols-[minmax(200px,280px)_minmax(0,1fr)]"
              key={account.account_id}
            >
              <div className="min-w-0">
                <h4 className="font-semibold break-words">
                  {[account.holder, account.identifier]
                    .filter(Boolean)
                    .join(" · ") || "Account details not recorded"}
                </h4>
                <p className="text-[12.5px] text-muted-foreground">
                  {account.institution || "Bank not recorded"}
                  {account.currency ? ` · ${account.currency}` : ""}
                </p>
              </div>
              <div className="min-w-0 space-y-2">
              {(!account.available || !account.currencies.length) && (
                <p className="font-medium text-[#8a5300]">
                  {!account.available
                    ? account.reason || "Statement dates could not be checked."
                    : account.periods.length === 0
                      ? "No saved statement periods for this account yet."
                      : "Saved statements need the checks below before their months can be counted."}
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
                const covered = coverage.months.length - missing.length - partial.length
                return (
                  <div key={group.currency} className="space-y-1.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <p className="font-medium">
                        {group.currency} · {missing.length} of{" "}
                        {coverage.months.length} months missing
                        {partial.length
                          ? ` · ${partial.length} months have gaps`
                          : ""}
                      </p>
                      <span
                        className={`tabular-nums text-[13px] font-semibold ${covered === coverage.months.length ? "text-[#15653f]" : "text-[#8a5300]"}`}
                      >
                        {covered}/{coverage.months.length} months
                      </span>
                    </div>
                    <ul
                      className="grid gap-1"
                      style={{ gridTemplateColumns: `repeat(${Math.min(coverage.months.length, 24)}, minmax(10px, 1fr))` }}
                      aria-label={`${group.currency} statement months`}
                    >
                      {coverage.months.map((month) => {
                        const text = `${displayMonth(month.month)} · ${
                          month.status === "covered"
                            ? "Covered"
                            : month.status === "partial"
                              ? "Some dates missing"
                              : "Missing"
                        }`
                        return (
                          <li key={month.month} className="h-[22px]">
                            <button
                              type="button"
                              title={`${text}. ${month.status === "missing" ? "Click to check these dates" : "Click to open the statement"}`}
                              aria-label={text}
                              className="block size-full rounded hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
                              style={cell(month.status)}
                              onClick={() =>
                                openMonth({
                                  account,
                                  label:
                                    [account.holder, account.identifier]
                                      .filter(Boolean)
                                      .join(" · ") ||
                                    "Account details not recorded",
                                  currency: group.currency,
                                  month: month.month,
                                  status: month.status,
                                })
                              }
                            >
                              <span className="sr-only">{text}</span>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                    <p className="text-[13px] text-muted-foreground">
                      Range checked: {displayDate(coverage.start)} to{" "}
                      {displayDate(coverage.end)}.
                    </p>
                    {missing.length > 0 && (
                      <p className="text-[13px] font-medium text-[#8a5300] dark:text-[#f2c46b]">
                        Missing:{" "}
                        {missing
                          .map((month) => displayMonth(month.month))
                          .join(", ")}
                        .
                      </p>
                    )}
                    {partial.length > 0 && (
                      <p className="text-[13px] font-medium text-[#8a5300] dark:text-[#f2c46b]">
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
              {account.periods.some((period) => !period.included) && (
                <Disclosure
                  label={`${account.periods.filter((period) => !period.included).length} saved statement periods need checking`}
                >
                  {account.periods
                    .filter((period) => !period.included)
                    .map((period) => (
                      <div key={period.period_id} className="mt-3 space-y-1 rounded-lg bg-[#fdf0d5] p-3 text-[#5c3800]">
                        <p className="font-medium">
                          {period.currency} ·{" "}
                          {period.start && period.end
                            ? `${displayDate(period.start)} to ${displayDate(period.end)}`
                            : "Statement dates not recorded"}
                        </p>
                        <p>
                          {
                            {
                              source_not_admitted:
                                "This statement is excluded from the saved payments and month counts.",
                              missing_dates:
                                "Add the start and end dates printed on the statement.",
                              dates_not_printed:
                                "Check the saved dates against the original statement before counting these months.",
                              invalid_date_range:
                                "The saved end date is before the start date. Correct the dates from the original.",
                            }[period.exclusion_reason || "missing_dates"]
                          }
                        </p>
                        {period.evidence_file_id && (
                          <Button
                            variant="outline"
                            onClick={() =>
                              navigate(
                                `/cases/${caseId}/financial?view=statements&files=1&reviewFile=${encodeURIComponent(period.evidence_file_id!)}`
                              )
                            }
                          >
                            Review statement dates
                          </Button>
                        )}
                        {period.filename && (
                          <p className="text-xs">
                            Source: {period.filename}
                          </p>
                        )}
                      </div>
                    ))}
                </Disclosure>
              )}
              </div>
            </li>
          ))}
          </ul>
          <p className="text-[13px] text-muted-foreground">
            Earlier and later months have not been checked. Files still waiting
            to be saved may fill these gaps. Use account review to check a
            specific date range.
          </p>
          {(offset > 0 || query.data.has_more) && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] text-muted-foreground">
                Accounts {offset + 1}–{offset + query.data.items.length}
                {query.data.has_more ? ", more after these" : ""}
              </span>
              <Button
                variant="outline"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 25))}
              >
                Previous accounts
              </Button>
              <Button
                variant="outline"
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
      <Dialog open={!!opened} onOpenChange={(open) => !open && setOpened(null)}>
        {opened && (
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle>
                {opened.label} · {opened.currency} ·{" "}
                {displayMonth(opened.month)}
              </DialogTitle>
              <DialogDescription>
                {opened.status === "missing"
                  ? "No saved statement covers this month."
                  : opened.status === "partial"
                    ? "Saved statements cover part of this month."
                    : "Saved statements that cover this month."}
              </DialogDescription>
            </DialogHeader>
            {opened.status === "missing" ? (
              <RequestedCoveragePanel
                caseId={caseId}
                params={{
                  accountId: opened.account.account_id,
                  startDate: `${opened.month}-01`,
                  endDate: monthEnd(opened.month),
                }}
                accountLabel={opened.label}
                autoLoad
              />
            ) : (
              <ul className="space-y-3 text-sm">
                {periodsInMonth(opened).map((period) => (
                  <li key={period.period_id} className="space-y-1.5 rounded-lg border p-3">
                    <p className="font-medium break-words">
                      {period.filename || "Saved statement"}
                    </p>
                    <p className="text-muted-foreground">
                      {displayDate(period.start!)} to {displayDate(period.end!)}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {period.evidence_file_id && (
                        <Button onClick={() => reviewFile(period.evidence_file_id!)}>
                          Open statement
                        </Button>
                      )}
                      <StatementSourceButton
                        caseId={caseId}
                        periodId={period.period_id}
                        sourceDocumentId={period.source_document_id}
                        label="Open statement and dates"
                        onReviewStatement={reviewFile}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </DialogContent>
        )}
      </Dialog>
    </section>
  )
}
