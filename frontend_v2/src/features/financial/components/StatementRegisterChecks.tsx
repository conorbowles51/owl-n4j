import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CalendarRange, Copy, TriangleAlert } from "lucide-react"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import {
  statementCoverage,
  type StatementCoverageAccount,
} from "../lib/statement-coverage"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import {
  AccountStatementReview,
  type AccountReviewDates,
} from "./AccountStatementReview"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"

function issues(account: StatementCoverageAccount) {
  return {
    gaps: account.currencies.flatMap((group) =>
      group.gaps.map((gap) => ({ ...gap, currency: group.currency }))
    ),
    overlaps: account.currencies.flatMap((group) => group.overlaps),
    unknown: account.periods.filter(
      (period) =>
        !period.included && period.exclusion_reason !== "source_not_admitted"
    ),
  }
}

export function StatementRegisterChecks({
  caseId,
  onOpenTransactions,
  onReviewStatement,
}: {
  caseId: string
  onOpenTransactions: (accountId: string, dates?: AccountReviewDates) => void
  onReviewStatement?: (fileId: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<StatementCoverageAccount | null>(
    null
  )
  const [duplicates, setDuplicates] = useState(false)
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "coverage", undefined, offset],
    retry: false,
    queryFn: async () => {
      const data = statementCoverage.parse(
        await fetchAPI(
          `${candidateUrl("statement-coverage", caseId)}&offset=${offset}`
        )
      )
      assertCandidateScope(data, caseId)
      if (data.offset !== offset || data.account_id)
        throw Error("The account list changed. Refresh the checks.")
      return data
    },
  })
  const accounts = query.isError ? [] : (query.data?.items ?? [])
  const gapAccounts = accounts.filter((account) => issues(account).gaps.length)
  const overlapAccounts = accounts.filter(
    (account) => issues(account).overlaps.length
  )
  const unknownAccounts = accounts.filter(
    (account) =>
      !account.available ||
      !account.currencies.length ||
      issues(account).unknown.length
  )
  return (
    <section
      aria-label="Account statement checks"
      className="finance-panel rounded-xl border p-4 space-y-4"
      data-finance-tone="source"
    >
      <div className="flex flex-wrap justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <CalendarRange className="h-4 w-4" />
            Do you have all the statements?
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Checks the dates of imported statements. Files still being reviewed
            are not counted yet.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDuplicates(true)}
          >
            <Copy className="h-4 w-4" />
            Check duplicate imports
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            Refresh date checks
          </Button>
        </div>
      </div>
      {query.isPending ? (
        <p role="status">Checking imported statement dates…</p>
      ) : query.isError ? (
        <p role="alert">
          Statement dates could not be checked. {query.error.message} Use
          Refresh date checks to retry.
        </p>
      ) : !accounts.length ? (
        <p className="text-sm">
          {offset
            ? "No more accounts on this page. Use Previous accounts to return."
            : "No accounts have been recorded. Import a statement to check its dates here."}
        </p>
      ) : (
        <>
          <div
            className="grid gap-3 sm:grid-cols-3 text-sm"
            aria-label="Statement date summary"
          >
            {[
              [gapAccounts.length, "Accounts with gaps"],
              [overlapAccounts.length, "Accounts with overlapping dates"],
              [unknownAccounts.length, "Accounts with dates still to check"],
            ].map(([count, label]) => (
              <div
                key={label}
                className="finance-panel rounded-lg border p-3"
                data-finance-tone={count ? "review" : "source"}
              >
                <p className="font-semibold text-xl">{count}</p>
                <p>{label}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {offset > 0 || query.data.has_more
              ? "Counts cover the accounts on this page. "
              : ""}
            Gaps are checked between the first and last imported statements.
            Open an account to check earlier or later dates. Overlapping dates
            can mean repeated or additional records.
          </p>
          <ul className="divide-y rounded-lg border bg-background">
            {accounts.map((account) => {
              const checks = issues(account)
              const label =
                [account.holder, account.identifier]
                  .filter(Boolean)
                  .join(" · ") || account.label
              return (
                <li key={account.account_id} className="p-3 space-y-2">
                  <div className="flex flex-wrap justify-between items-start gap-2">
                    <div className="min-w-0">
                      <p className="font-medium break-words">{label}</p>
                      <p className="text-xs text-muted-foreground">
                        {account.institution || "Bank not recorded"}
                        {account.currency ? ` · ${account.currency}` : ""}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      aria-label={`Review dates for ${label}`}
                      onClick={() => setSelected(account)}
                    >
                      Review dates & statements
                    </Button>
                  </div>
                  {!account.available ? (
                    <p className="text-sm">
                      {account.reason || "Dates could not be checked."}
                    </p>
                  ) : (
                    <>
                      {account.currencies.map((group) => (
                        <p key={group.currency} className="text-sm">
                          {group.currency}: {group.period_count} imported
                          statement{" "}
                          {group.period_count === 1 ? "period" : "periods"}
                          {group.windows.length
                            ? `, ${group.windows[0].start} to ${group.windows.at(-1)!.end}`
                            : ""}
                          .
                        </p>
                      ))}
                      {!!checks.gaps.length && (
                        <div
                          className="finance-panel rounded border p-2 text-sm"
                          data-finance-tone="review"
                        >
                          <p className="font-medium flex gap-2 items-center">
                            <TriangleAlert className="h-4 w-4" />
                            Missing statement dates
                          </p>
                          {checks.gaps.slice(0, 3).map((gap) => (
                            <p key={`${gap.currency}:${gap.start}`}>
                              {gap.start} to {gap.end} · {gap.days}{" "}
                              {gap.days === 1 ? "day" : "days"} · {gap.currency}
                            </p>
                          ))}
                          {checks.gaps.length > 3 && (
                            <p>
                              {checks.gaps.length - 3} more gaps. Open Review
                              dates & statements to see them all.
                            </p>
                          )}
                        </div>
                      )}
                      {!!checks.overlaps.length && (
                        <p className="text-sm font-medium">
                          {checks.overlaps.length} overlapping statement{" "}
                          {checks.overlaps.length === 1 ? "period" : "periods"}.
                          Review the statements before excluding a copy.
                        </p>
                      )}
                      {!!checks.unknown.length && (
                        <p className="text-sm">
                          {checks.unknown.length} statement{" "}
                          {checks.unknown.length === 1
                            ? "period has"
                            : "periods have"}{" "}
                          missing, unconfirmed or invalid dates. Open the
                          statements to check them.
                        </p>
                      )}
                      {!account.currencies.length ? (
                        <p className="text-sm">
                          No usable imported statement dates. This account’s
                          coverage is unknown.
                        </p>
                      ) : (
                        !checks.gaps.length &&
                        !checks.overlaps.length &&
                        !checks.unknown.length && (
                          <p className="text-sm text-muted-foreground">
                            No gaps or overlaps between these statements.
                            Earlier and later dates have not been checked.
                          </p>
                        )
                      )}
                    </>
                  )}
                </li>
              )
            })}
          </ul>
        </>
      )}
      {(offset > 0 || query.data?.has_more) && (
        <div className="flex flex-wrap gap-3 items-center text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={!offset || query.isFetching}
            onClick={() => setOffset((value) => Math.max(0, value - 25))}
          >
            Previous accounts
          </Button>
          <span>Account page {offset / 25 + 1}</span>
          <Button
            variant="outline"
            size="sm"
            disabled={
              !query.data?.has_more || query.isFetching || query.isError
            }
            onClick={() => setOffset((value) => value + 25)}
          >
            Next accounts
          </Button>
        </div>
      )}
      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null)
        }}
      >
        <DialogContent className="sm:max-w-5xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Account statements and missing dates</DialogTitle>
            <DialogDescription>
              Open the original statements, inspect overlaps or check the full
              date range you need.
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <AccountStatementReview
              key={`${caseId}:${selected.account_id}`}
              caseId={caseId}
              datesFirst
              onReviewStatement={
                onReviewStatement
                  ? (fileId) => {
                      setSelected(null)
                      onReviewStatement(fileId)
                    }
                  : undefined
              }
              account={{
                id: selected.account_id,
                holder: selected.holder ?? null,
                identifier: selected.identifier ?? selected.label,
                institution: selected.institution ?? null,
                currency: selected.currency ?? null,
              }}
              onBack={() => setSelected(null)}
              onOpenTransactions={(dates) => {
                onOpenTransactions(selected.account_id, dates)
                setSelected(null)
              }}
            />
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={duplicates} onOpenChange={setDuplicates}>
        <DialogContent className="sm:max-w-5xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Check duplicate imports</DialogTitle>
            <DialogDescription>
              Compare statements already imported into this case. Excluding a
              copy keeps the original file in Evidence.
            </DialogDescription>
          </DialogHeader>
          {duplicates && (
            <DuplicateCandidatesPanel
              key={caseId}
              caseId={caseId}
              autoLoad
              showCrossCase={false}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
