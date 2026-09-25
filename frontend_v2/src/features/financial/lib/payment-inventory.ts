import type { LedgerTransaction } from "../api"
import { bankKey } from "./account-selection"
import { paymentDay } from "./investigator-workspace"

/** Complete matching rows, never the visible table page. */
export function paymentInventory(rows: LedgerTransaction[]) {
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
