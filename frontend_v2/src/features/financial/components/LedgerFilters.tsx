import { useFinancialDraft } from "../stores/financial-drafts"
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

/** Explicit submission keeps draft dates/account searches separate from the answer. */
export function LedgerFilters({
  caseId,
  onApply,
  accountOnly = false,
  draftName,
}: {
  caseId: string
  draftName?: string
  accountOnly?: boolean
  onApply: (params: LedgerQueryParams) => void
}) {
  const [saved, setSaved] = useFinancialDraft(
    caseId,
    draftName ?? "ledger-filters",
    {
      search: "",
      account: null as { id: string; label: string } | null,
      start: "",
      end: "",
    }
  )
  const [local, setLocal] = useState(saved)
  const { search, account, start, end } = draftName ? saved : local
  const update = draftName ? setSaved : setLocal
  const setSearch = (search: string) =>
    update((previous) => ({ ...previous, search }))
  const setAccount = (account: { id: string; label: string } | null) =>
    update((previous) => ({ ...previous, account }))
  const setStart = (start: string) =>
    update((previous) => ({ ...previous, start }))
  const setEnd = (end: string) => update((previous) => ({ ...previous, end }))
  const [requestedSearch, setRequestedSearch] = useState<string | null>(null)
  const accounts = useQuery({
    queryKey: ["financial-ledger", caseId, "filter-accounts", requestedSearch],
    enabled: requestedSearch !== null,
    retry: false,
    queryFn: async () => {
      const data = candidateAccounts.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("ledger-accounts", caseId)}&${new URLSearchParams({ search: requestedSearch ?? "" })}`
        )
      )
      assertCandidateScope(data, caseId)
      return data
    },
  })
  const reversed = Boolean(start && end && start > end)
  return (
    <section
      aria-label="Ledger filters"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">
        {accountOnly ? "Choose an account" : "Choose the account and dates"}
      </h3>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (requestedSearch === search) void accounts.refetch()
          else setRequestedSearch(search)
        }}
      >
        <label>
          Search accounts
          <input
            className="block rounded border p-2"
            value={search}
            maxLength={128}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <Button type="submit" variant="outline" disabled={accounts.isFetching}>
          Find accounts
        </Button>
      </form>
      {accounts.isFetching && <p role="status">Finding accounts…</p>}
      {accounts.isError && (
        <p role="alert">Accounts unavailable. {accounts.error.message}</p>
      )}
      {accounts.isSuccess && !accounts.isFetching && (
        <div className="space-y-2">
          <p>Account results for: {requestedSearch || "all accounts"}.</p>
          {accounts.data.items.map((item) => {
            const label =
              [
                item.display_label,
                item.identifier,
                item.holder,
                item.institution,
                item.currency,
              ]
                .filter(Boolean)
                .join(" · ") || item.id
            return (
              <Button
                type="button"
                variant="outline"
                key={item.id}
                onClick={() => setAccount({ id: item.id, label })}
              >
                Select {label}
                {item.provisional ? " (account details need checking)" : ""}
              </Button>
            )
          })}
          {accounts.data.items.length === 0 && (
            <p>
              No imported account matches this search. Try part of the account
              number, holder name or bank name.
            </p>
          )}
          {accounts.data.has_more && (
            <p>More accounts are available. Narrow the account search.</p>
          )}
        </div>
      )}
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          if (!reversed)
            onApply({
              accountId: account?.id,
              startDate: accountOnly ? undefined : start || undefined,
              endDate: accountOnly ? undefined : end || undefined,
            })
        }}
      >
        <p>Selected account: {account?.label ?? "All accounts"}</p>
        <Button
          type="button"
          variant="outline"
          onClick={() => setAccount(null)}
        >
          Use all accounts
        </Button>
        {!accountOnly && (
          <>
            <div className="flex flex-wrap gap-3">
              <label>
                From date
                <input
                  className="block rounded border p-2"
                  type="date"
                  min="0001-01-01"
                  max="9999-12-31"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </label>
              <label>
                To date
                <input
                  className="block rounded border p-2"
                  type="date"
                  min="0001-01-01"
                  max="9999-12-31"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </label>
            </div>
            <p>
              The range includes both dates. It uses each payment's ordering
              date, which may differ from its printed transaction date. Open a
              payment's date details to check which source date is used.
            </p>
          </>
        )}
        {reversed && (
          <p role="alert">The start date must be on or before the end date.</p>
        )}
        <div className="flex gap-2">
          <Button type="submit" disabled={reversed}>
            {accountOnly ? "Use selected account" : "Apply account and dates"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setAccount(null)
              setStart("")
              setEnd("")
              onApply({})
            }}
          >
            {accountOnly ? "Clear selected account" : "Reset account and dates"}
          </Button>
        </div>
        <p>
          Apply your account and dates to update the result. The selected range
          is shown with the payments.
        </p>
      </form>
    </section>
  )
}
