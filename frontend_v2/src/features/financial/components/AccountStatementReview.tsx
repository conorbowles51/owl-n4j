import { useState } from "react"
import { Button } from "@/components/ui/button"
import { StatementChecksPanel } from "./StatementChecksPanel"
import { StatementCoveragePanel } from "./StatementCoveragePanel"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"

export type AccountReviewDates = { startDate?: string; endDate?: string }

function validDay(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const time = Date.parse(`${value}T00:00:00Z`)
  return (
    Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value
  )
}

export function AccountStatementReview({
  caseId,
  account,
  onBack,
  onOpenTransactions,
}: {
  caseId: string
  account: {
    id: string
    holder: string | null
    identifier: string | null
    institution: string | null
    currency: string | null
  }
  onBack: () => void
  onOpenTransactions: (dates?: AccountReviewDates) => void
}) {
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [range, setRange] = useState<{
    startDate: string
    endDate: string
  } | null>(null)
  const [checkNumber, setCheckNumber] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const label =
    [account.holder, account.identifier].filter(Boolean).join(" · ") ||
    "Account details not recorded"
  return (
    <section aria-label="Account statement review" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" onClick={onBack}>
          Back to accounts
        </Button>
        <Button onClick={() => onOpenTransactions()}>
          View all account transactions
        </Button>
      </div>
      <header>
        <h3 className="text-lg font-semibold">{label}</h3>
        <p className="text-sm text-muted-foreground">
          {account.institution || "Bank not recorded"} ·{" "}
          {account.currency || "Currency not recorded"}
        </p>
        <p className="mt-2 text-sm">
          Review this account’s statements below. A balance difference needs
          investigation; missing dates show where another statement may be
          needed.
        </p>
      </header>
      <StatementChecksPanel
        caseId={caseId}
        accountId={account.id}
        autoLoad
        onOpenTransactions={(startDate, endDate) =>
          onOpenTransactions(
            startDate && endDate ? { startDate, endDate } : undefined
          )
        }
      />
      <StatementCoveragePanel caseId={caseId} accountId={account.id} autoLoad />
      <section
        aria-label="Check a date range"
        className="space-y-3 rounded border p-4"
      >
        <h3 className="font-semibold">
          Do you have statements for the dates you need?
        </h3>
        <p className="text-sm">
          Enter the first and last dates you want to investigate. This includes
          dates before the earliest statement and after the latest.
        </p>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!validDay(start) || !validDay(end) || start > end) {
              setError("Enter a valid start date on or before the end date.")
              return
            }
            setError(null)
            setRange({ startDate: start, endDate: end })
            setCheckNumber((value) => value + 1)
          }}
        >
          <label className="text-sm">
            From
            <input
              type="date"
              required
              aria-label="Statement check from"
              className="block rounded border bg-background p-2"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label className="text-sm">
            To
            <input
              type="date"
              required
              aria-label="Statement check to"
              className="block rounded border bg-background p-2"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
          </label>
          <Button type="submit">Check date range</Button>
        </form>
        {error && <p role="alert">{error}</p>}
        {range && (
          <>
            {(start !== range.startDate || end !== range.endDate) && (
              <p role="status" className="text-sm">
                Dates changed. Select Check date range to update the results
                below.
              </p>
            )}
            <RequestedCoveragePanel
              key={checkNumber}
              caseId={caseId}
              params={{ accountId: account.id, ...range }}
              accountLabel={label}
              autoLoad
            />
            <Button variant="outline" onClick={() => onOpenTransactions(range)}>
              View transactions in the checked date range
            </Button>
          </>
        )}
      </section>
    </section>
  )
}
