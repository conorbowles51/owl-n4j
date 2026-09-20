import type { LedgerTransaction } from "../api"
import { holderKey } from "../lib/account-holder"

export function TransactionAccountFilters({
  rows,
  accountId,
  accountHolder,
  onChange,
}: {
  rows: LedgerTransaction[]
  accountId: string
  accountHolder: string
  onChange: (values: { accountId: string; accountHolder: string }) => void
}) {
  const holders = new Map<string, string>()
  const accounts = new Map<string, string>()
  for (const row of rows) {
    const holder = holderKey(row.account_holder)
    if (holder && !holders.has(holder))
      holders.set(holder, row.account_holder!.trim().replace(/\s+/g, " "))
    if (row.account_id && (!accountHolder || holder === accountHolder))
      accounts.set(row.account_id, row.account_label || row.account_id)
  }
  return (
    <div
      className="flex flex-wrap items-end gap-3"
      aria-label="Filter imported accounts"
    >
      <label className="min-w-52 flex-1">
        Person or company
        <select
          aria-label="Filter account holder"
          className="block w-full rounded border bg-background p-2"
          value={accountHolder}
          onChange={(e) =>
            onChange({ accountHolder: e.target.value, accountId: "" })
          }
        >
          <option value="">All account holders</option>
          {accountHolder && !holders.has(accountHolder) && (
            <option value={accountHolder}>{accountHolder}</option>
          )}
          {[...holders]
            .sort((a, b) => a[1].localeCompare(b[1]))
            .map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
        </select>
      </label>
      <label className="min-w-64 flex-1">
        Bank account
        <select
          aria-label="Filter imported account"
          className="block w-full rounded border bg-background p-2"
          value={accountId}
          onChange={(e) =>
            onChange({ accountHolder, accountId: e.target.value })
          }
        >
          <option value="">
            {accountHolder
              ? "All this holder’s accounts, across banks"
              : "All accounts, across banks"}
          </option>
          {accountId && !accounts.has(accountId) && (
            <option value={accountId}>
              Selected account (outside this view)
            </option>
          )}
          {[...accounts]
            .sort((a, b) => a[1].localeCompare(b[1]))
            .map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
        </select>
      </label>
      {accountHolder && (
        <p className="basis-full text-xs text-muted-foreground">
          Grouped by the recorded account holder name.
        </p>
      )}
    </div>
  )
}
