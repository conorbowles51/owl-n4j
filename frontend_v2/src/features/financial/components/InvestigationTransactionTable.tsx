import { openPaymentParty } from "../lib/payment-party-navigation"
import { chartRatio } from "../lib/investigator-workspace"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import { Button } from "@/components/ui/button"

export function PaymentTotals({
  rows,
  label,
}: {
  rows: LedgerTransaction[]
  label: string
}) {
  const totals = new Map<string, { credit: bigint; debit: bigint }>()
  let unreadable = 0
  for (const row of rows) {
    if (
      !/^\d+$/.test(String(row.amount_minor)) ||
      (typeof row.amount_minor === "number" &&
        !Number.isSafeInteger(row.amount_minor)) ||
      !["credit", "debit"].includes(row.direction)
    ) {
      unreadable++
      continue
    }
    const group = `${row.currency}:${row.account_type === "credit_card" ? "card" : "bank"}`
    const total = totals.get(group) ?? { credit: 0n, debit: 0n }
    total[row.direction as "credit" | "debit"] += BigInt(row.amount_minor)
    totals.set(group, total)
  }
  return (
    <section
      aria-label={label}
      className="space-y-2 rounded border bg-card p-3"
    >
      <h3 className="text-sm font-medium">
        {label} · {rows.length} transactions
      </h3>
      {[...totals].map(([group, total]) => {
        const [currency, kind] = group.split(":")
        return (
          <dl
            key={group}
            className="finance-metrics grid grid-cols-3 gap-3 text-sm"
          >
            {[
              [kind === "card" ? "Card credits" : "Money in", total.credit],
              [kind === "card" ? "Card charges" : "Money out", total.debit],
              ["Difference", total.credit - total.debit],
            ].map(([title, amount], index) => (
              <div
                key={String(title)}
                className="finance-metric"
                data-finance-tone={["credit", "debit", "info"][index]}
              >
                <dt className="text-muted-foreground">{String(title)}</dt>
                <dd className="font-semibold">
                  {formatLedgerAmount(String(amount), currency).text} {currency}
                </dd>
                {index < 2 && (
                  <div
                    role="img"
                    aria-label={`${String(title)} compared with ${index === 0 ? "outgoing" : "incoming"} amounts`}
                    className="mt-2 h-3 rounded bg-background/70"
                  >
                    <div
                      className="h-full rounded"
                      style={{
                        width: `${chartRatio(BigInt(amount), total.credit > total.debit ? total.credit || 1n : total.debit || 1n) * 100}%`,
                        backgroundColor: `var(--finance-${index === 0 ? "credit" : "debit"})`,
                      }}
                    />
                  </div>
                )}
              </div>
            ))}
          </dl>
        )
      })}
      {rows.some((row) => row.account_type === "credit_card") && (
        <p className="text-xs">
          Card charges increase the amount owed. Card credits reduce it. They
          are shown separately from bank payments.
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
            {hasBalance && <th className="p-2 text-right">Balance</th>}
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
                  {row.from_name ||
                    (row.direction === "debit"
                      ? row.account_label
                      : row.counterparty_raw) ||
                    "Not recorded"}
                </button>
              </td>
              <td className="p-2 max-w-44 break-words">
                <button
                  className="text-left underline underline-offset-2 decoration-muted-foreground/40"
                  onClick={() => openPaymentParty(row.case_id, row, "to")}
                >
                  {row.to_name ||
                    (row.direction === "credit"
                      ? row.account_label
                      : row.counterparty_raw) ||
                    "Not recorded"}
                </button>
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
                  {row.running_balance_minor === null
                    ? "Not recorded"
                    : money(row.running_balance_minor, row.currency)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
