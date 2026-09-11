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
          <dl key={group} className="grid grid-cols-3 gap-3 text-sm">
            {[
              [kind === "card" ? "Card credits" : "Money in", total.credit],
              [kind === "card" ? "Card charges" : "Money out", total.debit],
              ["Difference", total.credit - total.debit],
            ].map(([title, amount]) => (
              <div key={String(title)}>
                <dt className="text-muted-foreground">{String(title)}</dt>
                <dd className="font-semibold">
                  {formatLedgerAmount(String(amount), currency).text} {currency}
                </dd>
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
}: {
  rows: LedgerTransaction[]
  selected: string[]
  onToggle: (row: LedgerTransaction, checked: boolean) => void
  onOpen?: (row: LedgerTransaction) => void
  onNote?: (row: LedgerTransaction) => void
}) {
  const cards = rows.some((row) => row.account_type === "credit_card")
  const money = (value: string | number, currency: string) =>
    `${formatLedgerAmount(value, currency).text} ${currency}`
  return (
    <div className="overflow-x-auto rounded border">
      <table className="w-full text-sm" aria-label="Investigation transactions">
        <thead className="bg-muted/40 text-left">
          <tr>
            <th className="p-2">
              <span className="sr-only">Select</span>
            </th>
            <th className="p-2">Date</th>
            <th className="p-2">Description</th>
            <th className="p-2 text-right">{cards ? "Credit" : "Money in"}</th>
            <th className="p-2 text-right">{cards ? "Debit" : "Money out"}</th>
            <th className="p-2 text-right">Balance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t align-top hover:bg-muted/20">
              <td className="p-2">
                <input
                  type="checkbox"
                  aria-label={`Select ${row.description || row.ref_id} on ${row.ordering_date}`}
                  checked={selected.includes(row.key)}
                  onChange={(event) => onToggle(row, event.target.checked)}
                />
              </td>
              <td className="p-2 whitespace-nowrap">
                {row.ordering_date}
                {row.ordering_date_context ===
                  "statement_end_ordering_only" && (
                  <p className="text-xs whitespace-normal">
                    Statement end date
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
                {row.account_type === "credit_card" && (
                  <p className="text-xs">
                    Credit card:{" "}
                    {row.direction === "credit"
                      ? "reduces amount owed"
                      : "increases amount owed"}
                  </p>
                )}
                {row.counterparty_raw && (
                  <p className="text-xs text-muted-foreground">
                    {row.counterparty_raw}
                  </p>
                )}
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
              </td>
              <td className="p-2 text-right tabular-nums">
                {row.direction === "credit"
                  ? money(row.amount_minor, row.currency)
                  : ""}
              </td>
              <td className="p-2 text-right tabular-nums">
                {row.direction === "debit"
                  ? money(row.amount_minor, row.currency)
                  : ""}
              </td>
              <td className="p-2 text-right tabular-nums">
                {row.running_balance_minor === null
                  ? "Not recorded"
                  : money(row.running_balance_minor, row.currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
