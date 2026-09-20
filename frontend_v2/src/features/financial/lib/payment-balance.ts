import type { LedgerTransaction } from "../api"

export function absentPaymentBalance(row: LedgerTransaction): string {
  return row.balance_status === "not_printed" ? "Not printed" : "Not available"
}

export function paymentBalanceExplanation(row: LedgerTransaction): string {
  return row.balance_status === "not_printed"
    ? "This statement does not print a balance beside this entry. Opening and closing balances are shown with the statement when available."
    : "No balance was extracted for this entry. Open the original statement to check whether one is printed."
}
