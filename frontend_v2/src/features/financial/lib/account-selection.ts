import { holderKey } from "./account-holder"
import type { LedgerTransaction } from "../api"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

export type AccountSelection = Pick<
  LedgerQueryParams,
  "accountId" | "accountIds" | "accountHolders"
>
export const bankKey = (value?: string | null) => {
  const token = holderKey(value || "")
  return (
    (
      {
        "bbva mexico": "bbva",
        "bbva méxico": "bbva",
        "bbva bancomer": "bbva",
        "banco santander mexico": "santander",
        "banco santander méxico": "santander",
      } as Record<string, string>
    )[token] || token
  )
}
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
  const holders = (scope.accountHolders ?? []).filter(
    (value) => !value.startsWith("bank:")
  )
  const banks = (scope.accountHolders ?? []).filter((value) =>
    value.startsWith("bank:")
  )
  return (
    [
      banks.length
        ? `${banks.length} selected ${banks.length === 1 ? "bank" : "banks"}`
        : "",
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
  const holders = (scope.accountHolders ?? []).filter(
    (value) => !value.startsWith("bank:")
  )
  const banks = (scope.accountHolders ?? []).filter((value) =>
    value.startsWith("bank:")
  )
  return (
    (!ids.length ||
      ids.includes(row.account_id) ||
      (!!row.canonical_account_id && ids.includes(row.canonical_account_id)) ||
      (row.account_alias_ids ?? []).some((id) => ids.includes(id))) &&
    (!banks.length ||
      banks.includes(`bank:${bankKey(row.account_institution)}`)) &&
    (!holders.length ||
      holders.includes(holderKey(row.account_holder)) ||
      (!!row.account_party_id &&
        holders.includes(`party:${row.account_party_id}`)) ||
      (row.account_holder_parties ?? []).some((p) =>
        holders.includes(`party:${p.id}`)
      ))
  )
}
