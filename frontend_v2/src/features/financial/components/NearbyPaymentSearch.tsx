import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useLedgerTransactions } from "../hooks/use-ledger-transactions"
import { paymentDay } from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import { useFinancialDraft } from "../stores/financial-drafts"
import { PaymentComparison } from "./PaymentComparison"

export function NearbyPaymentSearch({
  caseId,
  row,
}: {
  caseId: string
  row: LedgerTransaction
}) {
  const [open, setOpen] = useState(false)
  const [view, setView] = useFinancialDraft(
    caseId,
    `related-payments:${row.key}`,
    {
      days: 7,
      interval: "after",
      selected: [row.key],
      page: 0,
    }
  )
  const { days, interval, selected, page } = view
  const [compare, setCompare] = useState(false)
  const date = paymentDay(row)
  const shifted = (offset: number) => {
    const value = new Date(`${date}T00:00:00Z`)
    value.setUTCDate(value.getUTCDate() + offset)
    return value.toISOString().slice(0, 10)
  }
  const startDate = date
    ? shifted(interval === "around" ? -days : 0)
    : undefined
  const endDate = date ? shifted(days) : undefined
  const query = useLedgerTransactions(open && date ? caseId : undefined, {
    accountId: row.account_id,
    startDate,
    endDate,
  })
  const complete =
    !!query.data &&
    query.data.case_id === caseId &&
    query.data.total === query.data.transactions.length &&
    new Set(query.data.transactions.map((item) => item.key)).size ===
      query.data.total &&
    query.data.transactions.every(
      (item) => item.case_id === caseId && item.account_id === row.account_id
    )
  const rows = complete
    ? query
        .data!.transactions.filter((item) => {
          const day = paymentDay(item)
          return (
            day && day >= startDate! && day <= endDate! && item.key !== row.key
          )
        })
        .sort((a, b) => paymentDay(a)!.localeCompare(paymentDay(b)!))
    : []
  const visible = new Set([row.key, ...rows.map((item) => item.key)])
  const chosen = [...new Set([row.key, ...selected])]
  const hidden = chosen.filter((id) => !visible.has(id)).length
  const index = Math.min(page, Math.max(0, Math.ceil(rows.length / 10) - 1))
  if (!date) return null
  return (
    <section className="space-y-3 text-sm">
      <Button variant="outline" onClick={() => setOpen(!open)}>
        {open ? "Close related payments" : "Related payments"}
      </Button>
      {open && (
        <div className="space-y-3 rounded border bg-background p-3">
          <div className="flex flex-wrap items-end gap-2">
            <label>
              Look for
              <select
                aria-label="Related payment interval"
                className="block rounded border bg-background p-2"
                value={interval}
                onChange={(e) =>
                  setView((previous) => ({
                    ...previous,
                    interval: e.target.value,
                    page: 0,
                  }))
                }
              >
                <option value="after">Payments after this one</option>
                <option value="around">Payments before and after</option>
              </select>
            </label>
            <label>
              Within
              <select
                aria-label="Related payment days"
                className="block rounded border bg-background p-2"
                value={days}
                onChange={(e) =>
                  setView((previous) => ({
                    ...previous,
                    days: Number(e.target.value),
                    page: 0,
                  }))
                }
              >
                {[1, 3, 7, 14, 30].map((value) => (
                  <option key={value} value={value}>
                    {value} days
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            Same account · {startDate} to {endDate}. This search includes
            payments outside the main table’s filters. Dates alone do not
            establish a transfer.
          </p>
          {query.isPending ? (
            <p role="status">Loading related payments…</p>
          ) : query.isError || !complete ? (
            <div role="alert">
              <p>Related payments could not be fully loaded.</p>
              <Button variant="outline" onClick={() => void query.refetch()}>
                Try again
              </Button>
            </div>
          ) : (
            <>
              <p className="font-medium">
                {rows.length} other payments · current payment included in
                comparison
              </p>
              <div className="divide-y">
                {rows.slice(index * 10, index * 10 + 10).map((item) => (
                  <label
                    key={item.key}
                    className="flex cursor-pointer items-start gap-2 py-2"
                  >
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={chosen.includes(item.key)}
                      aria-label={`Compare ${item.description} on ${paymentDay(item)}`}
                      onChange={(e) =>
                        setView((previous) => ({
                          ...previous,
                          selected: e.target.checked
                            ? [...new Set([...previous.selected, item.key])]
                            : previous.selected.filter((id) => id !== item.key),
                        }))
                      }
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block">{item.description}</span>
                      <span className="text-xs text-muted-foreground">
                        {paymentDay(item)}
                      </span>
                    </span>
                    <span
                      className="finance-amount text-right"
                      data-finance-tone={item.direction}
                    >
                      {
                        formatLedgerAmount(item.amount_minor, item.currency)
                          .text
                      }{" "}
                      {item.currency}
                      <span className="block text-xs">
                        {item.account_type === "credit_card"
                          ? item.direction === "credit"
                            ? "Card credit"
                            : "Card charge"
                          : item.direction === "credit"
                            ? "Money in"
                            : "Money out"}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
              {rows.length > 10 && (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!index}
                    onClick={() =>
                      setView((previous) => ({ ...previous, page: index - 1 }))
                    }
                  >
                    Previous related payments
                  </Button>
                  <span>
                    {index * 10 + 1}–{Math.min(index * 10 + 10, rows.length)} of{" "}
                    {rows.length}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={(index + 1) * 10 >= rows.length}
                    onClick={() =>
                      setView((previous) => ({ ...previous, page: index + 1 }))
                    }
                  >
                    Next related payments
                  </Button>
                </div>
              )}
              {!!hidden && (
                <p>
                  {hidden} selected payments are outside this interval. They
                  remain in the comparison.
                </p>
              )}
              <div className="flex gap-2">
                <Button
                  disabled={chosen.length < 2}
                  onClick={() => setCompare(true)}
                >
                  Compare {chosen.length} selected payments
                </Button>
                {chosen.length > 1 && (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setView((previous) => ({
                        ...previous,
                        selected: [row.key],
                      }))
                    }
                  >
                    Clear related selection
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      )}
      {compare && complete && (
        <PaymentComparison
          caseId={caseId}
          ids={chosen}
          title="Compare related payments"
          onClose={() => setCompare(false)}
        />
      )}
    </section>
  )
}
