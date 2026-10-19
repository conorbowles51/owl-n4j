import { paymentInventory } from "../lib/payment-inventory"
import { knownAccountGroup, type KnownPaymentAccount } from "../lib/known-payment-accounts"
import { openPaymentParty } from "../lib/payment-party-navigation"
import { paymentGroup } from "../lib/investigator-workspace"
import { amountGroupName, amountOf } from "../lib/transaction-analysis"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import { Button } from "@/components/ui/button"
import { useRef, useState } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { AccountHistory } from "./AccountHistory"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import {
  absentPaymentBalance,
  paymentBalanceExplanation,
} from "../lib/payment-balance"

export function PaymentTotals({
  rows,
  label,
  expandAccounts = true,
  knownAccounts = [],
  caseId,
}: {
  rows: LedgerTransaction[]
  label: string
  expandAccounts?: boolean
  knownAccounts?: KnownPaymentAccount[]
  caseId?: string
}) {
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
    total.accounts.add(row.canonical_account_id || row.account_id)
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
  const groupName = (group: string) => group.endsWith(":unknown")
    ? `${group.split(":")[0]} · Account type not recorded`
    : amountGroupName(group)
  const unknownCurrencyCount = new Set(knownAccounts.filter((account) => !account.currency).map((account) => account.id)).size
  return (
    <section
      aria-label={label}
      className="space-y-3 rounded border bg-card p-3"
    >
      <h3 className="text-sm font-medium">
        {label} · {rows.length.toLocaleString()} transactions ·{" "}
        {inventory.accounts.length} accounts · {inventory.banks.length} banks
      </h3>
      <p className="text-xs text-muted-foreground">
        Currencies: {inventory.currencies.join(", ") || (unknownCurrencyCount ? "Not recorded" : "None")}. Dated payments:{" "}
        {inventory.first
          ? `${inventory.first} to ${inventory.last}`
          : "No printed dates available"}
        .
        {inventory.undated > 0 &&
          ` ${inventory.undated} payments without a printed date.`}
        {inventory.unknownBanks > 0 &&
          ` ${inventory.unknownBanks} accounts with bank not identified.`}
        {inventory.unidentifiedCounterparties > 0 &&
          ` ${inventory.unidentifiedCounterparties} payments with counterparty not identified.`}
      </p>
      {knownAccounts.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Account counts include known accounts in this account/date scope, even when no payments match your filters.
          Amounts come only from matching imported payments; zero does not confirm no activity or completed processing.
        </p>
      )}
      {unknownCurrencyCount > 0 && (
        <p className="text-xs" aria-label="Accounts with currency not recorded">
          Currency is not recorded for {unknownCurrencyCount} known {unknownCurrencyCount === 1 ? "account" : "accounts"}. These accounts are included in the account and bank counts; no zero amount or currency has been assumed.
        </p>
      )}
      {expandAccounts && inventory.accounts.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer">
            View all {inventory.accounts.length} accounts and{" "}
            {inventory.banks.length} banks
          </summary>
          <p className="mt-2">
            Banks: {inventory.banks.join(", ") || "Not identified"}
          </p>
          <ul className="max-h-48 overflow-auto mt-2 space-y-1">
            {inventory.accounts.map((account) => (
              <li key={account.id}>
                {account.label} · {[...account.currencies].sort().join(", ") || "Currency not recorded"}
                {caseId && knownAccounts.some((known) => known.id === account.id) && (
                  <KnownAccountHistory key={`${caseId}:${account.id}`} caseId={caseId} accountId={account.id} label={account.label} />
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {[...totals].map(([group, total]) => {
        const [currency, kind] = group.split(":")
        const card = kind === "card"
        const unknown = kind === "unknown"
        const net = card
          ? total.debit - total.credit
          : total.credit - total.debit
        return (
          <section
            key={group}
            aria-label={groupName(group)}
            className="space-y-1"
          >
            <div className="flex flex-wrap items-center gap-x-3 text-xs">
              <h4 className="font-semibold">{groupName(group)}</h4>
              <span className="text-muted-foreground">
                {total.count.toLocaleString()} transactions ·{" "}
                {total.accounts.size}{" "}
                {total.accounts.size === 1 ? "account" : "accounts"}
              </span>
            </div>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              {[
                [
                  card ? "Card credits" : unknown ? "Credits" : "Money in",
                  total.credit,
                  card ? "Reduce card debt" : unknown ? "Recorded credits" : "Received by these accounts",
                ],
                [
                  card ? "Card charges" : unknown ? "Debits" : "Money out",
                  total.debit,
                  card ? "Increase card debt" : unknown ? "Recorded debits" : "Paid from these accounts",
                ],
                [
                  card ? "Change in card debt" : unknown ? "Net credits" : "Net movement",
                  net,
                  card ? "Charges minus credits" : unknown ? "Credits minus debits" : "Money in minus money out",
                ],
              ].map(([title, amount, help], index) => (
                <div
                  key={String(title)}
                  className="rounded-md border px-3 py-2"
                  style={{
                    backgroundColor: `color-mix(in srgb, var(--finance-${["credit", "debit", "info"][index]}) 8%, transparent)`,
                  }}
                >
                  <dt className="text-xs text-muted-foreground">
                    {String(title)}
                  </dt>
                  <dd className="font-semibold tabular-nums">
                    {formatLedgerAmount(String(amount), currency).text}{" "}
                    {currency}
                  </dd>
                  <div className="text-[11px] text-muted-foreground">
                    {String(help)}
                  </div>
                </div>
              ))}
            </dl>
            {total.count === 0 && (
              <p className="text-xs text-muted-foreground">
                No matching imported payments. {knownAccounts.some((account) => total.accounts.has(account.id) && account.currency === currency && account.periods.length)
                  ? "Saved statements are available. Review account history to check their balances, dates and no-activity confirmation."
                  : "No saved statement period is recorded for these accounts in this scope. Check Statements & accounts for pending reading or review."}
              </p>
            )}
          </section>
        )
      })}
      {totals.size > 1 && (
        <p className="text-xs text-muted-foreground">
          Each row is a separate currency and account type. These amounts are
          not added together.
        </p>
      )}
      {unreadable > 0 && (
        <p>
          {unreadable} transactions could not be totalled. Open them to check
          the amount and whether money went in or out.
        </p>
      )}
    </section>
  )
}

function KnownAccountHistory({ caseId, accountId, label }: { caseId: string; accountId: string; label: string }) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  return <>
    <Button ref={trigger} size="sm" variant="link" aria-label={`View account history for ${label}`} onClick={() => setOpen(true)}>View account history</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-auto" onCloseAutoFocus={(event) => { event.preventDefault(); trigger.current?.focus({ preventScroll: true }) }}>
        <DialogHeader>
          <DialogTitle>{label}</DialogTitle>
          <DialogDescription>Saved statements, balance observations and activity checks for this account. Close to return to the same transaction filters.</DialogDescription>
        </DialogHeader>
        {open && <AccountHistory caseId={caseId} accountId={accountId} />}
      </DialogContent>
    </Dialog>
  </>
}

export function InvestigationTransactionTable({
  rows,
  selected,
  onToggle,
  onOpen,
  onNote,
  onCategorize,
  compact = false,
  showAccount,
  findings = [],
}: {
  findings?: { tags: string[]; payment_ids: string[] }[]
  compact?: boolean
  showAccount?: boolean
  rows: LedgerTransaction[]
  selected: string[]
  onToggle: (row: LedgerTransaction, checked: boolean) => void
  onOpen?: (row: LedgerTransaction) => void
  onNote?: (row: LedgerTransaction) => void
  onCategorize?: (row: LedgerTransaction) => void
}) {
  const selectedIds = new Set(selected)
  const notes = new Map<string, { count: number; followUp: boolean }>()
  for (const finding of findings)
    for (const id of finding.payment_ids) {
      const value = notes.get(id) ?? { count: 0, followUp: false }
      value.count++
      value.followUp ||=
        finding.tags.includes("financial-question") &&
        !finding.tags.includes("financial-complete")
      notes.set(id, value)
    }
  const multipleAccounts = new Set(rows.map((row) => row.account_id)).size > 1
  const hasBalance = rows.some((row) => row.running_balance_minor != null)
  const cards = rows.some((row) => row.account_type === "credit_card")
  const money = (value: string | number, currency: string) =>
    `${formatLedgerAmount(value, currency).text} ${currency}`
  return (
    <div className="overflow-x-auto rounded border">
      <table
        className="finance-table w-full text-sm"
        aria-label="Investigation transactions"
      >
        <thead className="bg-muted/40 text-left">
          <tr>
            <th className="p-2">
              <span className="sr-only">Select</span>
            </th>
            <th className="p-2">Date</th>
            <th className="p-2">Description</th>
            <th className="p-2">From</th>
            <th className="p-2">To</th>
            <th className="p-2">Category</th>
            <th className="p-2 text-right">{cards ? "Credit" : "Money in"}</th>
            <th className="p-2 text-right">{cards ? "Debit" : "Money out"}</th>
            {hasBalance && <th className="p-2 text-right">Printed balance</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              data-selected={selectedIds.has(row.key)}
              className="border-t align-top"
            >
              <td className="p-2">
                <input
                  type="checkbox"
                  aria-label={`Select ${row.description || row.ref_id} ${row.ordering_date_context === "statement_end_ordering_only" ? `with no printed date, statement ending ${row.ordering_date}` : `on ${row.ordering_date}`}`}
                  checked={selectedIds.has(row.key)}
                  onChange={(event) => onToggle(row, event.target.checked)}
                />
              </td>
              <td className="p-2 whitespace-nowrap">
                {row.ordering_date_context === "statement_end_ordering_only"
                  ? "Date not printed"
                  : row.ordering_date}
                {row.ordering_date_context ===
                  "statement_end_ordering_only" && (
                  <p className="text-xs whitespace-normal">
                    Statement ends {row.ordering_date}
                  </p>
                )}
              </td>
              <td className="p-2 min-w-48 max-w-sm">
                <button
                  className="text-left font-medium underline underline-offset-2"
                  onClick={() => onOpen?.(row)}
                >
                  {row.description || "Open transaction"}
                </button>
                {notes.has(row.key) && (
                  <p
                    className="finance-badge mt-1"
                    data-finance-tone={
                      notes.get(row.key)!.followUp ? "review" : "work"
                    }
                  >
                    {notes.get(row.key)!.followUp
                      ? "Follow-up question · "
                      : ""}
                    {notes.get(row.key)!.count} linked findings
                  </p>
                )}
                {row.account_type === "credit_card" && (
                  <p className="text-xs">
                    Credit card:{" "}
                    {row.direction === "credit"
                      ? "reduces amount owed"
                      : "increases amount owed"}
                  </p>
                )}
                {!compact && row.counterparty_raw && (
                  <p className="text-xs text-muted-foreground">
                    {row.counterparty_raw}
                  </p>
                )}
                {row.account_label &&
                  (!compact || showAccount || multipleAccounts) && (
                    <p className="text-xs text-muted-foreground break-words">
                      Account: {row.account_label}
                    </p>
                  )}
                {!compact && (
                  <div className="mt-1 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onOpen?.(row)}
                    >
                      Open transaction
                    </Button>
                    {onNote && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onNote(row)}
                      >
                        Add note
                      </Button>
                    )}
                  </div>
                )}
              </td>
              <td className="p-2 max-w-44 break-words">
                <button
                  className="text-left underline underline-offset-2 decoration-muted-foreground/40"
                  onClick={() => openPaymentParty(row.case_id, row, "from")}
                >
                  {(row.from_name ??
                    (row.direction === "debit"
                      ? row.account_label
                      : row.counterparty_raw)) ||
                    "Not identified"}
                </button>
                <PaymentLabelOrigin row={row} field="from_name" />
              </td>
              <td className="p-2 max-w-44 break-words">
                <button
                  className="text-left underline underline-offset-2 decoration-muted-foreground/40"
                  onClick={() => openPaymentParty(row.case_id, row, "to")}
                >
                  {(row.to_name ??
                    (row.direction === "credit"
                      ? row.account_label
                      : row.counterparty_raw)) ||
                    "Not identified"}
                </button>
                <PaymentLabelOrigin row={row} field="to_name" />
              </td>
              <td className="p-2">
                <button
                  className="finance-badge underline underline-offset-2 text-left"
                  data-finance-tone="work"
                  aria-label={`Change category for ${row.description || row.ref_id}`}
                  onClick={() =>
                    onCategorize ? onCategorize(row) : onOpen?.(row)
                  }
                >
                  {row.category || "Uncategorized"}
                </button>
                <PaymentLabelOrigin row={row} field="category" />
              </td>
              <td
                className="finance-amount p-2 text-right tabular-nums"
                data-finance-tone="credit"
              >
                {row.direction === "credit"
                  ? money(row.amount_minor, row.currency)
                  : ""}
              </td>
              <td
                className="finance-amount p-2 text-right tabular-nums"
                data-finance-tone="debit"
              >
                {row.direction === "debit"
                  ? money(row.amount_minor, row.currency)
                  : ""}
              </td>
              {hasBalance && (
                <td className="p-2 text-right tabular-nums">
                  {row.running_balance_minor == null ? (
                    <span title={paymentBalanceExplanation(row)}>
                      {absentPaymentBalance(row)}
                    </span>
                  ) : (
                    money(row.running_balance_minor, row.currency)
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
