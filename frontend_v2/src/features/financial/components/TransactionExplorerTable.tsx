import { needsName, otherSide } from "../lib/payment-naming"
import { Fragment, useState } from "react"
import { readProofClass } from "../lib/ledger-format"
import { OPTIONAL_COLUMNS, type OptionalColumn } from "../lib/table-columns"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import { party, type PartySide } from "../lib/transaction-analysis"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import { RowJudgementMarkers, priorityRowClass } from "./JudgementCalls"
import { useRowPriority } from "../hooks/use-judgement-rows"
import type { ReactNode } from "react"
import { cn } from "@/lib/cn"

/** A payment row; in a list of judgement calls it carries its tier's tint and left border. */
function PriorityRow({ row, className, children }: { row: LedgerTransaction; className: string; children: ReactNode }) {
  const priority = useRowPriority(row)
  return (
    <tr data-priority={priority || undefined} className={priority ? cn(className, priorityRowClass(priority)) : className}>
      {children}
    </tr>
  )
}
import {
  absentPaymentBalance,
  paymentBalanceExplanation,
} from "../lib/payment-balance"

/** "Columns (8 of 15) ▾": a checkbox per optional column and Reset to default. */
export function TableColumnPicker({
  columns,
  onChange,
}: {
  columns: OptionalColumn[]
  onChange: (columns: OptionalColumn[]) => void
}) {
  const [open, setOpen] = useState(false)
  const fixed = 6
  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-[13px] font-semibold hover:bg-muted"
      >
        Columns ({fixed + columns.length} of {fixed + OPTIONAL_COLUMNS.length}) <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div role="group" aria-label="Table columns" className="absolute right-0 z-20 mt-1 w-60 space-y-1 rounded-xl border bg-card p-3 text-sm shadow-lg">
          <p className="text-[12px] text-muted-foreground">Always shown: select, date, description, from → to, category, amount</p>
          {OPTIONAL_COLUMNS.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={columns.includes(key)}
                onChange={(event) =>
                  onChange(
                    OPTIONAL_COLUMNS.map(([k]) => k).filter((k) => (k === key ? event.target.checked : columns.includes(k)))
                  )
                }
              />
              {label}
            </label>
          ))}
          <button type="button" className="mt-1 text-[13px] font-semibold text-[#1d4aa6] hover:underline dark:text-[#9bb8f0]" onClick={() => onChange([])}>
            Reset to default
          </button>
        </div>
      )}
    </div>
  )
}

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
  categoryColors,
  onParty,
  onName,
  nameAction = "Name it",
  findings = [],
  amountAllowed = true,
  columns = [],
  statementNames,
}: {
  columns?: OptionalColumn[]
  statementNames?: Map<string, string>
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
  categoryColors?: Map<string, string>
  onParty: (side: PartySide, key: string) => void
  onName?: (row: LedgerTransaction) => void
  /** The inline action on a side without a name: "Name it", or "See the line" for a viewer. */
  nameAction?: string
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
        style={{ minWidth: 640 + columns.length * 120 }}
        aria-label="Investigation transactions"
      >
        <colgroup>
          <col style={{ width: 32 }} />
          <col style={{ width: 96 }} />
          <col style={{ width: "32%" }} />
          <col style={{ width: "24%" }} />
          <col style={{ width: "17%" }} />
          <col style={{ width: 136 }} />
          {columns.map((key) => (
            <col key={key} style={{ width: 120 }} />
          ))}
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
              {!amountAllowed && (
                <span className="block text-[12px] font-normal text-muted-foreground">Choose one currency to sort amounts</span>
              )}
            </th>
            {columns.map((key) => (
              <th key={key} className="p-2">
                {OPTIONAL_COLUMNS.find(([k]) => k === key)?.[1]}
              </th>
            ))}
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
                <PriorityRow
                  row={row}
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
                    <RowJudgementMarkers transaction={row} />
                    {onEdit && (
                      <button
                        className="mt-1 rounded border px-2 py-1 text-xs font-medium hover:bg-muted"
                        onClick={() => onEdit(row)}
                      >
                        Edit transaction
                      </button>
                    )}
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
                          ? " · observation"
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
                          title={
                            onName && needsName(row) && otherSide(row) === (side === "from" ? "from_name" : "to_name")
                              ? `${nameAction}: open the statement line beside the table`
                              : `Filter ${side}: ${party(row, side).name}`
                          }
                          onClick={() =>
                            onName && needsName(row) && otherSide(row) === (side === "from" ? "from_name" : "to_name")
                              ? onName(row)
                              : onParty(side, party(row, side).key)
                          }
                        >
                          {party(row, side).name}
                        </button>
                        <PaymentLabelOrigin
                          row={row}
                          field={side === "from" ? "from_name" : "to_name"}
                        />
                        {onName && needsName(row) && otherSide(row) === (side === "from" ? "from_name" : "to_name") && (
                          <button
                            className="ml-1 text-xs font-medium text-[#1d4aa6] hover:underline dark:text-blue-300"
                            aria-label={`${nameAction} ${side === "from" ? "who paid" : "who was paid"}: ${row.description || row.ref_id} on ${row.ordering_date}`}
                            onClick={() => onName(row)}
                          >
                            {nameAction}
                          </button>
                        )}
                      </div>
                    ))}
                  </td>
                  <td className="p-2 break-words">
                    <button
                      className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-left font-medium hover:bg-muted ${row.category ? "bg-background" : "border-dashed text-muted-foreground"}`}
                      aria-label={`Change category for ${row.description || row.ref_id}`}
                      onClick={() =>
                        onCategory ? onCategory(row) : onOpen?.(row)
                      }
                    >
                      {row.category &&
                        categoryColors?.get(row.category.toLowerCase()) && (
                          <span
                            aria-hidden="true"
                            className="size-2 shrink-0 rounded-full"
                            style={{
                              backgroundColor: categoryColors.get(
                                row.category.toLowerCase()
                              ),
                            }}
                          />
                        )}
                      <span className="truncate">
                        {row.category || "Uncategorized"}
                      </span>
                    </button>
                    <PaymentLabelOrigin row={row} field="category" />
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
                  {columns.map((key) => (
                    <td key={key} className="p-2 break-words">
                      {key === "reference"
                        ? row.ref_id || row.key
                        : key === "bank_reference"
                          ? row.bank_reference || "Not recorded"
                          : key === "account"
                            ? row.account_label || row.account_id
                            : key === "balance"
                              ? row.running_balance_minor == null
                                ? absentPaymentBalance(row)
                                : money(row.running_balance_minor, row.currency)
                              : key === "statement"
                                ? statementNames?.get(row.source_document_id) || `Statement ${row.source_document_id.slice(0, 8)}`
                                : key === "proof"
                                  ? (() => {
                                      const term = readProofClass(row.proof_class)
                                      return <span title={term.description}>{term.label}</span>
                                    })()
                                  : row.currency}
                    </td>
                  ))}
                </PriorityRow>
                {open && (
                  <tr className="border-t bg-muted/30">
                    <td colSpan={6 + columns.length} className="p-3">
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
                              Edit transaction
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
