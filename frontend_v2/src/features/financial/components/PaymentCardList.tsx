import type { LedgerTransaction } from "../api"
import { categoryTone } from "../lib/category-palette"
import { formatLedgerAmount } from "../lib/ledger-format"
import { absentPaymentBalance, paymentBalanceExplanation } from "../lib/payment-balance"
import { party, type PartySide } from "../lib/transaction-analysis"
import { RowJudgementMarkers } from "./JudgementCalls"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"

const AVATARS = ["#3a6fd8", "#0f8a7e", "#7b52c7", "#c67a10", "#c4456b", "#2f9353", "#1789a6", "#4b5bd6"]
const initials = (name: string) =>
  name
    .replace(/[^\p{L}\p{N} ]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]!.toUpperCase())
    .join("") || "?"
const hue = (name: string) => AVATARS[[...name].reduce((sum, c) => (sum * 31 + c.charCodeAt(0)) >>> 0, 7) % AVATARS.length]

const dayOf = (row: LedgerTransaction) =>
  row.ordering_date_context === "statement_end_ordering_only" ? "" : row.ordering_date || ""
const dayHeading = (day: string) => {
  if (!day) return "Date not printed"
  const date = new Date(`${day}T00:00:00Z`)
  return Number.isNaN(date.getTime())
    ? day
    : date.toLocaleDateString("en", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
}

/**
 * The roomy default rows of the Transactions view: one card per payment, grouped by day, with the counterparty,
 * category, judgement calls and amount readable at a glance and every table field one click away in Details.
 */
export function PaymentCardList({
  rows,
  selected,
  expanded,
  onExpand,
  onToggle,
  onOpen,
  onNote,
  onEdit,
  onCategory,
  categoryColors,
  onParty,
  findings = [],
}: {
  rows: LedgerTransaction[]
  selected: string[]
  expanded: string[]
  onExpand: (ids: string[]) => void
  onToggle: (row: LedgerTransaction, checked: boolean) => void
  onOpen?: (row: LedgerTransaction) => void
  onNote?: (row: LedgerTransaction) => void
  onEdit?: (row: LedgerTransaction) => void
  onCategory?: (row: LedgerTransaction) => void
  categoryColors?: Map<string, string>
  onParty: (side: PartySide, key: string) => void
  findings?: { title?: string | null; tags: string[]; payment_ids: string[] }[]
}) {
  const selectedIds = new Set(selected)
  const expandedIds = new Set(expanded)
  const money = (value: string | number, currency: string) => `${formatLedgerAmount(value, currency).text} ${currency}`
  // Rows arrive in the chosen sort; consecutive payments of one day share a heading.
  const days: { day: string; rows: LedgerTransaction[] }[] = []
  for (const row of rows) {
    const day = dayOf(row)
    if (days.at(-1)?.day === day) days.at(-1)!.rows.push(row)
    else days.push({ day, rows: [row] })
  }
  return (
    <div className="space-y-5" role="list" aria-label="Investigation transactions">
      {days.map(({ day, rows: dayRows }, groupIndex) => (
        <div key={`${day}-${groupIndex}`} role="listitem" className="space-y-2">
          <h3 className="flex items-baseline gap-3 px-1 text-sm font-semibold">
            {dayHeading(day)}
            <span className="font-mono text-[11px] font-normal uppercase tracking-[0.08em] text-muted-foreground">
              {dayRows.length} {dayRows.length === 1 ? "payment" : "payments"}
            </span>
          </h3>
          <ul className="space-y-2">
            {dayRows.map((row) => {
              const open = expandedIds.has(row.key)
              const checked = selectedIds.has(row.key)
              const incoming = row.direction === "credit"
              const other = party(row, incoming ? "from" : "to")
              const own = party(row, incoming ? "to" : "from")
              const tone = categoryTone(row.category || "", row.category ? categoryColors?.get(row.category.toLowerCase()) : undefined)
              const rowFindings = findings.filter((f) => f.payment_ids.includes(row.key))
              const label = row.description || row.ref_id
              return (
                <li
                  key={row.key}
                  className={`rounded-xl border bg-card shadow-sm transition-colors ${checked ? "border-[#3a6fd8] bg-[#3a6fd8]/5" : "hover:border-foreground/25"}`}
                >
                  <div className="grid grid-cols-[auto_auto_minmax(0,1fr)] items-start gap-3 p-3 sm:grid-cols-[auto_auto_minmax(0,1fr)_auto_auto] sm:items-center sm:p-4">
                    <input
                      type="checkbox"
                      className="mt-1 size-4 sm:mt-0"
                      aria-label={`Select ${label} on ${row.ordering_date}`}
                      checked={checked}
                      onChange={(e) => onToggle(row, e.target.checked)}
                    />
                    <span
                      aria-hidden="true"
                      className="flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
                      style={{ background: hue(other.name) }}
                    >
                      {initials(other.name)}
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <button
                          type="button"
                          className="truncate text-left text-[15px] font-semibold hover:underline"
                          title={`Filter ${incoming ? "from" : "to"}: ${other.name}`}
                          onClick={() => onParty(incoming ? "from" : "to", other.key)}
                        >
                          {other.name}
                        </button>
                        <PaymentLabelOrigin row={row} field={incoming ? "from_name" : "to_name"} />
                      </div>
                      <button
                        type="button"
                        className="block max-w-full truncate text-left text-[13px] text-muted-foreground hover:text-foreground hover:underline"
                        title={row.description ? `${row.description}. Open the original statement.` : "Open the original statement"}
                        onClick={() => onOpen?.(row)}
                      >
                        {row.description || "Open transaction"}
                      </button>
                      <span className="block truncate text-[12px] text-muted-foreground">
                        {incoming ? "Into " : "From "}
                        <button
                          type="button"
                          className="hover:underline"
                          title={`Filter ${incoming ? "to" : "from"}: ${own.name}`}
                          onClick={() => onParty(incoming ? "to" : "from", own.key)}
                        >
                          {own.name}
                        </button>
                        <PaymentLabelOrigin row={row} field={incoming ? "to_name" : "from_name"} />
                        {" · "}
                        <span title={row.account_label || row.account_id}>
                          {row.account_label || row.account_holder || row.account_id}
                        </span>
                      </span>
                      <RowJudgementMarkers transaction={row} />
                    </div>
                    <div className="col-start-3 flex flex-wrap items-center gap-1.5 sm:col-start-auto">
                      <button
                        type="button"
                        className={`inline-flex max-w-56 items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold hover:brightness-95 ${row.category ? "" : "border border-dashed border-[#d99a2b]"}`}
                        style={{ background: tone.tint, color: tone.text }}
                        aria-label={`Change category for ${label}`}
                        onClick={() => (onCategory ? onCategory(row) : onOpen?.(row))}
                      >
                        <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ background: tone.dot }} />
                        <span className="truncate">{row.category || "Uncategorized"}</span>
                      </button>
                      <PaymentLabelOrigin row={row} field="category" />
                    </div>
                    <div className="col-start-3 text-left sm:col-start-auto sm:min-w-36 sm:text-right">
                      <strong
                        className={`block whitespace-nowrap text-[17px] tabular-nums ${incoming ? "text-[#12784a] dark:text-[#5fd39a]" : "text-foreground"}`}
                        style={{ fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif" }}
                      >
                        {incoming ? "+" : "−"}
                        {money(row.amount_minor, row.currency)}
                      </strong>
                      <span className="block text-[11px] text-muted-foreground">
                        {row.account_type === "credit_card"
                          ? incoming
                            ? "Card credit"
                            : "Card charge"
                          : incoming
                            ? "Money in"
                            : "Money out"}
                      </span>
                      <button
                        type="button"
                        className="mt-0.5 text-[12px] font-medium text-[#1d4aa6] hover:underline dark:text-blue-300"
                        aria-expanded={open}
                        aria-label={`${open ? "Hide" : "Show"} details for ${label}`}
                        onClick={() => onExpand(open ? expanded.filter((id) => id !== row.key) : [...expanded, row.key])}
                      >
                        {open ? "▾" : "▸"} Details
                      </button>
                    </div>
                  </div>
                  {rowFindings.length > 0 && (
                    <button type="button" className="mx-4 mb-3 text-[12px] underline" onClick={() => onOpen?.(row)}>
                      {rowFindings.length} linked findings
                      {rowFindings.some((f) => f.tags.includes("financial-question") && !f.tags.includes("financial-complete"))
                        ? " · observation"
                        : ""}
                    </button>
                  )}
                  {open && (
                    <div className="space-y-2 border-t bg-muted/30 p-4 text-[13px]">
                      <p>{row.description}</p>
                      <dl className="flex flex-wrap gap-x-6 gap-y-2">
                        <div>
                          <dt className="text-muted-foreground">Date</dt>
                          <dd>{dayOf(row) || "Not printed"}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Reference</dt>
                          <dd>{row.ref_id || row.key}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Bank reference</dt>
                          <dd>{row.bank_reference || "Not recorded"}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Account</dt>
                          <dd>{row.account_label || row.account_id}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Printed balance</dt>
                          <dd title={paymentBalanceExplanation(row)}>
                            {row.running_balance_minor == null ? absentPaymentBalance(row) : money(row.running_balance_minor, row.currency)}
                          </dd>
                        </div>
                      </dl>
                      {rowFindings.map((f, i) => (
                        <p key={i}>Finding: {f.title || "Untitled"}</p>
                      ))}
                      <div className="flex flex-wrap gap-2">
                        <button type="button" className="rounded-md border bg-background px-3 py-1.5 font-medium hover:bg-muted" onClick={() => onOpen?.(row)}>
                          Open original statement
                        </button>
                        {onNote && (
                          <button type="button" className="rounded-md border bg-background px-3 py-1.5 font-medium hover:bg-muted" onClick={() => onNote(row)}>
                            Add note
                          </button>
                        )}
                        {onEdit && (
                          <button type="button" className="rounded-md border bg-background px-3 py-1.5 font-medium hover:bg-muted" onClick={() => onEdit(row)}>
                            Edit transaction
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}
