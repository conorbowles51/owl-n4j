import { Fragment } from "react"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import { party, type PartySide } from "../lib/transaction-analysis"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import {
  absentPaymentBalance,
  paymentBalanceExplanation,
} from "../lib/payment-balance"

export function TransactionExplorerTable({
  rows,
  selected,
  expanded,
  sort,
  onSort,
  onExpand,
  onToggle,
  onOpen,
  onNote,
  onEdit,
  onCategory,
  onParty,
  findings = [],
  amountAllowed = true,
}: {
  amountAllowed?: boolean
  rows: LedgerTransaction[]
  selected: string[]
  expanded: string[]
  sort: string
  onSort: (sort: string) => void
  onExpand: (ids: string[]) => void
  onToggle: (row: LedgerTransaction, checked: boolean) => void
  onOpen?: (row: LedgerTransaction) => void
  onNote?: (row: LedgerTransaction) => void
  onEdit?: (row: LedgerTransaction) => void
  onCategory?: (row: LedgerTransaction) => void
  onParty: (side: PartySide, key: string) => void
  findings?: { title?: string | null; tags: string[]; payment_ids: string[] }[]
}) {
  const selectedIds = new Set(selected),
    expandedIds = new Set(expanded)
  const header = (name: string, asc: string, desc: string, enabled = true) => (
    <button
      disabled={!enabled}
      className="text-left hover:underline disabled:no-underline"
      title={
        !enabled
          ? "Choose one currency to sort amounts"
          : `Sort by ${name.toLowerCase()}`
      }
      onClick={() => onSort(sort === asc ? desc : asc)}
    >
      {name}
      {sort === asc ? " ↑" : sort === desc ? " ↓" : " ↕"}
    </button>
  )
  const money = (value: string | number, currency: string) =>
    `${formatLedgerAmount(value, currency).text} ${currency}`
  return (
    <div className="min-w-0 max-h-[65vh] overflow-auto rounded border">
      <table
        className="w-full table-fixed text-xs"
        style={{ minWidth: 640 }}
        aria-label="Investigation transactions"
      >
        <colgroup>
          <col style={{ width: 32 }} />
          <col style={{ width: 96 }} />
          <col style={{ width: "32%" }} />
          <col style={{ width: "24%" }} />
          <col style={{ width: "17%" }} />
          <col style={{ width: 136 }} />
        </colgroup>
        <thead className="sticky top-0 z-10 bg-muted text-left">
          <tr>
            <th className="p-2">
              <span className="sr-only">Select</span>
            </th>
            <th className="p-2">{header("Date", "oldest", "newest")}</th>
            <th className="p-2">
              {header("Description", "description-asc", "description-desc")}
            </th>
            <th className="p-2">
              {header("From", "from-asc", "from-desc")} →{" "}
              {header("To", "to-asc", "to-desc")}
            </th>
            <th className="p-2">
              {header("Category", "category-asc", "category-desc")}
            </th>
            <th className="p-2 text-right">
              {header("Amount", "amount-asc", "amount-desc", amountAllowed)}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const rowFindings = findings.filter((f) =>
              f.payment_ids.includes(row.key)
            )
            const open = expandedIds.has(row.key)
            return (
              <Fragment key={row.key}>
                <tr
                  className={`border-t align-top ${selectedIds.has(row.key) ? "bg-primary/5" : ""}`}
                >
                  <td className="p-2">
                    <input
                      type="checkbox"
                      aria-label={`Select ${row.description || row.ref_id} on ${row.ordering_date}`}
                      checked={selectedIds.has(row.key)}
                      onChange={(e) => onToggle(row, e.target.checked)}
                    />
                  </td>
                  <td className="p-2">
                    <span className="whitespace-nowrap">
                      {row.ordering_date_context ===
                      "statement_end_ordering_only"
                        ? "Not printed"
                        : row.ordering_date}
                    </span>
                    <button
                      className="mt-1 block text-muted-foreground hover:underline"
                      aria-expanded={open}
                      aria-label={`${open ? "Hide" : "Show"} details for ${row.description || row.ref_id}`}
                      onClick={() =>
                        onExpand(
                          open
                            ? expanded.filter((id) => id !== row.key)
                            : [...expanded, row.key]
                        )
                      }
                    >
                      {open ? "▾" : "▸"} Details
                    </button>
                  </td>
                  <td className="p-2 break-words">
                    <button
                      className="line-clamp-2 text-left font-medium underline underline-offset-2"
                      title={row.description || undefined}
                      onClick={() => onOpen?.(row)}
                    >
                      {row.description || "Open transaction"}
                    </button>
                    <span
                      className="mt-1 block truncate text-[10px] text-muted-foreground"
                      title={row.account_label || row.account_id}
                    >
                      {row.account_label ||
                        row.account_holder ||
                        row.account_id}
                    </span>
                    {rowFindings.length > 0 && (
                      <button
                        className="mt-1 text-[10px] underline"
                        onClick={() => onOpen?.(row)}
                      >
                        {rowFindings.length} linked findings
                        {rowFindings.some(
                          (f) =>
                            f.tags.includes("financial-question") &&
                            !f.tags.includes("financial-complete")
                        )
                          ? " · follow-up"
                          : ""}
                      </button>
                    )}
                  </td>
                  <td className="p-2 break-words">
                    {(["from", "to"] as const).map((side) => (
                      <div key={side} className="mb-1">
                        <span className="text-muted-foreground">
                          {side === "from" ? "From " : "→ "}
                        </span>
                        <button
                          className="text-left hover:underline"
                          title={`Filter ${side}: ${party(row, side).name}`}
                          onClick={() => onParty(side, party(row, side).key)}
                        >
                          {party(row, side).name}
                        </button>
                        <PaymentLabelOrigin
                          row={row}
                          field={side === "from" ? "from_name" : "to_name"}
                        />
                      </div>
                    ))}
                  </td>
                  <td className="p-2 break-words">
                    <button
                      className="rounded border bg-primary/5 px-1.5 py-0.5 text-left hover:bg-primary/10"
                      aria-label={`Change category for ${row.description || row.ref_id}`}
                      onClick={() =>
                        onCategory ? onCategory(row) : onOpen?.(row)
                      }
                    >
                      {row.category || "Uncategorized"}
                    </button>
                    <PaymentLabelOrigin row={row} field="category" />
                    {onEdit && (
                      <button
                        className="mt-1 block text-[10px] text-muted-foreground underline"
                        onClick={() => onEdit(row)}
                      >
                        Edit names / category
                      </button>
                    )}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    <strong
                      className="whitespace-nowrap"
                      style={{
                        color:
                          row.direction === "credit"
                            ? "var(--finance-credit)"
                            : "var(--finance-debit)",
                      }}
                    >
                      {row.direction === "debit" ? "−" : "+"}
                      {money(row.amount_minor, row.currency)}
                    </strong>
                    <span className="block text-[10px] text-muted-foreground">
                      {row.account_type === "credit_card"
                        ? row.direction === "debit"
                          ? "Card charge"
                          : "Card credit"
                        : row.direction === "debit"
                          ? "Money out"
                          : "Money in"}
                    </span>
                  </td>
                </tr>
                {open && (
                  <tr className="border-t bg-muted/30">
                    <td colSpan={6} className="p-3">
                      <div className="space-y-2 text-xs">
                        <p>{row.description}</p>
                        <dl className="flex flex-wrap gap-x-6 gap-y-2">
                          <div>
                            <dt className="text-muted-foreground">Reference</dt>
                            <dd>{row.ref_id || row.key}</dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">
                              Bank reference
                            </dt>
                            <dd>{row.bank_reference || "Not recorded"}</dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">Account</dt>
                            <dd>{row.account_label || row.account_id}</dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">
                              Printed balance
                            </dt>
                            <dd title={paymentBalanceExplanation(row)}>
                              {row.running_balance_minor == null
                                ? absentPaymentBalance(row)
                                : money(
                                    row.running_balance_minor,
                                    row.currency
                                  )}
                            </dd>
                          </div>
                        </dl>
                        {rowFindings.map((f, i) => (
                          <p key={i}>Finding: {f.title || "Untitled"}</p>
                        ))}
                        <div className="flex flex-wrap gap-4">
                          <button
                            className="underline"
                            onClick={() => onOpen?.(row)}
                          >
                            Open original statement
                          </button>
                          {onNote && (
                            <button
                              className="underline"
                              onClick={() => onNote(row)}
                            >
                              Add note
                            </button>
                          )}
                          {onEdit && (
                            <button
                              className="underline"
                              onClick={() => onEdit(row)}
                            >
                              Edit names and category
                            </button>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
