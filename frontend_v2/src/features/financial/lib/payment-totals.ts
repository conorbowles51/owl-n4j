import type { LedgerTransaction } from "../api"
import { paymentAccountId } from "./account-selection"
import { paymentGroup } from "./investigator-workspace"
import { knownAccountGroup, type KnownPaymentAccount } from "./known-payment-accounts"
import { paymentInventory } from "./payment-inventory"
import { amountOf } from "./transaction-analysis"

const NO_KNOWN_ACCOUNTS: KnownPaymentAccount[] = []

/** PaymentTotals' figures from every matching payment: the payments, the inventory line, one total per currency and
 * account type, and the payments that cannot be totalled. */
export function paymentTotalsFigures(
  rows: LedgerTransaction[],
  knownAccounts: KnownPaymentAccount[] = NO_KNOWN_ACCOUNTS
) {
  const inventory = paymentInventory(rows, knownAccounts)
  const totals = new Map<
    string,
    {
      credit: bigint
      debit: bigint
      count: number
      accounts: Set<string>
      labels: Set<string>
    }
  >()
  let unreadable = 0
  for (const row of rows) {
    const amount = amountOf(row)
    if (amount === null) {
      unreadable++
      continue
    }
    const group = paymentGroup(row)
    const total = totals.get(group) ?? {
      credit: 0n,
      debit: 0n,
      count: 0,
      accounts: new Set<string>(),
      labels: new Set<string>(),
    }
    total[row.direction as "credit" | "debit"] += amount
    total.count++
    total.accounts.add(paymentAccountId(row))
    if (row.canonical_account_label || row.account_label)
      total.labels.add(row.canonical_account_label || row.account_label!)
    totals.set(group, total)
  }
  for (const account of knownAccounts) {
    if (!account.currency) continue
    // A directory alias never creates a second payment group for an account
    // whose actual rows already establish its currency/type in this scope.
    const observed = [...totals].find(([group, total]) => group.startsWith(`${account.currency}:`) && total.accounts.has(account.id))?.[0]
    const group = observed || knownAccountGroup(account)
    const total = totals.get(group) ?? { credit: 0n, debit: 0n, count: 0, accounts: new Set<string>(), labels: new Set<string>() }
    total.accounts.add(account.id)
    total.labels.add(account.label)
    totals.set(group, total)
  }
  return {
    payments: rows.length,
    inventory,
    totals: new Map([...totals].map(([group, total]) => [group, { ...total, accountCount: total.accounts.size }])),
    unreadable,
  }
}
