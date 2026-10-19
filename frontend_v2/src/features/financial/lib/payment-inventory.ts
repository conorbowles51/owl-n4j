import type { LedgerTransaction } from "../api"
import { bankKey } from "./account-selection"
import { paymentDay } from "./investigator-workspace"
import type { KnownPaymentAccount } from "./known-payment-accounts"

/** Complete matching rows, never the visible table page. */
export function paymentInventory(rows: LedgerTransaction[], knownAccounts: KnownPaymentAccount[] = []) {
  const accounts = new Map<
    string,
    { id: string; label: string; currencies: Set<string> }
  >()
  const banks = new Map<string, string>()
  const unknownBanks = new Set<string>()
  const currencies = new Set<string>()
  const dates: string[] = []
  let undated = 0,
    unidentifiedCounterparties = 0
  for (const row of rows) {
    const id = row.canonical_account_id || row.account_id
    const account = accounts.get(id) || {
      id,
      label:
        row.canonical_account_label ||
        row.account_label ||
        "Account details not recorded",
      currencies: new Set<string>(),
    }
    account.currencies.add(row.currency)
    accounts.set(id, account)
    const bank = row.account_institution?.trim()
    if (bank) banks.set(bankKey(bank), bank)
    else unknownBanks.add(id)
    currencies.add(row.currency)
    const day = paymentDay(row)
    if (day) dates.push(day)
    else undated++
    const name =
      (row.direction === "credit" ? row.from_name : row.to_name) ??
      row.counterparty_raw
    if (!name?.trim()) unidentifiedCounterparties++
  }
  for (const known of knownAccounts) {
    const account = accounts.get(known.id) ?? { id: known.id, label: known.label, currencies: new Set<string>() }
    if (known.currency) account.currencies.add(known.currency)
    accounts.set(known.id, account)
    if (known.currency) currencies.add(known.currency)
    if (known.institution?.trim()) {
      banks.set(bankKey(known.institution), known.institution.trim())
      unknownBanks.delete(known.id)
    } else if (!rows.some((row) => (row.canonical_account_id || row.account_id) === known.id && row.account_institution?.trim())) {
      unknownBanks.add(known.id)
    }
  }
  dates.sort()
  return {
    accounts: [...accounts.values()].sort((a, b) =>
      a.label.localeCompare(b.label)
    ),
    banks: [...banks.values()].sort(),
    currencies: [...currencies].sort(),
    first: dates[0] || null,
    last: dates.at(-1) || null,
    undated,
    unknownBanks: unknownBanks.size,
    unidentifiedCounterparties,
  }
}
