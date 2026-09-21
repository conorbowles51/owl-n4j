import { useState } from "react"
import { Button } from "@/components/ui/button"
import { TransactionAccountFilters } from "./TransactionAccountFilters"
import type { AccountSelection } from "../lib/account-selection"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

export function InvestigationFilters({
  caseId,
  onApply,
  initialParams = {},
  accountSelection = true,
}: {
  caseId: string
  initialParams?: LedgerQueryParams
  accountSelection?: boolean
  onApply: (p: LedgerQueryParams) => void
}) {
  const [selection, setSelection] = useState<AccountSelection>({
    accountId: initialParams.accountId,
    accountIds: initialParams.accountIds,
    accountHolders: initialParams.accountHolders,
  })
  const [start, setStart] = useState(initialParams.startDate ?? "")
  const [end, setEnd] = useState(initialParams.endDate ?? "")
  const invalid = !!start && !!end && start > end
  return (
    <form
      aria-label="Transaction account and dates"
      className="flex flex-wrap items-end gap-3 rounded border p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault()
        if (!invalid)
          onApply({
            ...selection,
            startDate: start || undefined,
            endDate: end || undefined,
          })
      }}
    >
      {accountSelection && (
        <TransactionAccountFilters
          caseId={caseId}
          selection={selection}
          onChange={setSelection}
        />
      )}
      <label>
        From
        <input
          aria-label="Transactions from"
          type="date"
          className="block rounded border p-2 bg-background"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </label>
      <label>
        To
        <input
          aria-label="Transactions to"
          type="date"
          className="block rounded border p-2 bg-background"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
        />
      </label>
      <Button type="submit" disabled={invalid}>
        Apply
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setSelection(accountSelection ? {} : selection)
          setStart("")
          setEnd("")
          onApply(accountSelection ? {} : selection)
        }}
      >
        Reset
      </Button>
      <details className="basis-full text-xs">
        <summary className="cursor-pointer">
          {accountSelection ? "Which dates are used" : "Which dates are used"}
        </summary>
        <p>
          The start and end dates are included. Payments without a transaction
          date are marked in the table. Check Statements for gaps in the
          documents supplied.
        </p>
      </details>
      {invalid && (
        <p role="alert">The start date must be on or before the end date.</p>
      )}
    </form>
  )
}
