import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import {
  candidateAccounts,
  candidateUrl,
  assertCandidateScope,
} from "../lib/candidate-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

export function InvestigationFilters({
  caseId,
  onApply,
  initialParams = {},
}: {
  caseId: string
  initialParams?: LedgerQueryParams
  onApply: (p: LedgerQueryParams) => void
}) {
  const [account, setAccount] = useState(initialParams.accountId ?? ""),
    [start, setStart] = useState(initialParams.startDate ?? ""),
    [end, setEnd] = useState(initialParams.endDate ?? ""),
    [search, setSearch] = useState("")
  const [selectedLabel, setSelectedLabel] = useState(
    initialParams.accountId ?? ""
  )
  const accounts = useQuery({
    queryKey: ["financial-ledger", caseId, "filter-accounts", search],
    retry: false,
    queryFn: async () => {
      const data = candidateAccounts.parse(
        await fetchAPI(
          `${candidateUrl("ledger-accounts", caseId)}&${new URLSearchParams({ search })}`
        )
      )
      assertCandidateScope(data, caseId)
      return data
    },
  })
  const invalid = !!start && !!end && start > end
  return (
    <form
      aria-label="Transaction account and dates"
      className="flex flex-wrap items-end gap-3 rounded border p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault()
        if (!invalid)
          onApply({
            accountId: account || undefined,
            startDate: start || undefined,
            endDate: end || undefined,
          })
      }}
    >
      <label className="min-w-56 flex-1">
        Account
        <select
          aria-label="Filter account"
          className="block w-full rounded border p-2 bg-background"
          value={account}
          onChange={(e) => {
            setAccount(e.target.value)
            setSelectedLabel(
              e.target.selectedOptions[0]?.textContent || e.target.value
            )
          }}
        >
          <option value="">All accounts</option>
          {account && !accounts.data?.items.some((a) => a.id === account) && (
            <option value={account}>{selectedLabel}</option>
          )}
          {accounts.data?.items.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_label ||
                [a.holder, a.identifier, a.institution]
                  .filter(Boolean)
                  .join(" · ") ||
                a.id}{" "}
              {a.currency}
            </option>
          ))}
        </select>
      </label>
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
          setAccount("")
          setStart("")
          setEnd("")
          onApply({})
        }}
      >
        Reset
      </Button>
      <details className="basis-full text-xs">
        <summary className="cursor-pointer">
          Find another account or inspect the date scope
        </summary>
        <label>
          Search account names or numbers
          <input
            aria-label="Search available accounts"
            className="ml-2 border rounded p-1 bg-background"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <p>
          Both dates are included. The table identifies which recorded date
          orders each transaction. Missing statements are shown under
          Statements.
        </p>
      </details>
      {invalid && (
        <p role="alert">The start date must be on or before the end date.</p>
      )}
      {accounts.isError && (
        <p role="alert">Account list unavailable. {accounts.error.message}</p>
      )}
    </form>
  )
}
