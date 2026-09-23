import { holderKey } from "./account-holder"
import type { LedgerTransaction } from "../api"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

export type AccountSelection = Pick<
  LedgerQueryParams,
  "accountId" | "accountIds" | "accountHolders"
>
export const selectedAccountIds = (scope: AccountSelection) =>
  scope.accountIds ?? (scope.accountId ? [scope.accountId] : [])

export function appendAccountSelection(
  search: URLSearchParams,
  scope: AccountSelection
) {
  for (const id of scope.accountIds ?? []) search.append("account_ids", id)
  for (const name of scope.accountHolders ?? [])
    search.append("account_holders", name)
}

export function accountSelectionSummary(scope: AccountSelection) {
  const accounts = selectedAccountIds(scope)
  const holders = scope.accountHolders ?? []
  return (
    [
      holders.length
        ? `${holders.length} ${holders.length === 1 ? "person or company" : "people or companies"}`
        : "",
      accounts.length
        ? `${accounts.length} selected ${accounts.length === 1 ? "account" : "accounts"}`
        : "",
    ]
      .filter(Boolean)
      .join(" · ") || "All accounts"
  )
}

export function matchesAccountSelection(
  row: LedgerTransaction,
  scope: AccountSelection
) {
  const ids = selectedAccountIds(scope)
  return (
    (!ids.length || ids.includes(row.account_id)) &&
    (!scope.accountHolders?.length ||
      scope.accountHolders.includes(holderKey(row.account_holder)) ||
      (!!row.account_party_id && scope.accountHolders.includes(`party:${row.account_party_id}`)) ||
      (row.account_holder_parties ?? []).some(p => scope.accountHolders!.includes(`party:${p.id}`)))
  )
}
