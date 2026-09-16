import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useLedgerTransactions } from "../hooks/use-ledger-transactions"
import { paymentDay } from "../lib/investigator-workspace"
import { PaymentComparison } from "./PaymentComparison"

export function NearbyPaymentSearch({
  caseId,
  row,
}: {
  caseId: string
  row: LedgerTransaction
}) {
  const [open, setOpen] = useState(false)
  const [days, setDays] = useState(7)
  const [compare, setCompare] = useState(false)
  const date = paymentDay(row)
  const shifted = (offset: number) => {
    const value = new Date(`${date}T00:00:00Z`)
    value.setUTCDate(value.getUTCDate() + offset)
    return value.toISOString().slice(0, 10)
  }
  const startDate = date ? shifted(-days) : undefined
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
    ? query.data!.transactions.filter((item) => {
        const day = paymentDay(item)
        return day && day >= startDate! && day <= endDate!
      })
    : []
  if (!date) return null
  return (
    <section className="space-y-3 text-sm">
      <Button variant="outline" onClick={() => setOpen(!open)}>
        {open ? "Hide nearby payments" : "Show nearby payments"}
      </Button>
      {open && (
        <div className="rounded border p-3 space-y-3">
          <label>
            Days before and after this payment{" "}
            <select
              className="rounded border bg-background p-2"
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              {[1, 3, 7, 14, 30].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <p>
            Same account · {startDate} to {endDate}. This uses payment dates,
            including entries outside the main table’s filters.
          </p>
          {query.isPending ? (
            <p role="status">Loading nearby payments…</p>
          ) : query.isError || !complete ? (
            <div role="alert">
              <p>Nearby payments could not be fully loaded.</p>
              <Button variant="outline" onClick={() => void query.refetch()}>
                Try again
              </Button>
            </div>
          ) : (
            <>
              <p>
                {rows.length} dated payments in this interval. Close dates do
                not establish a transfer.
              </p>
              <Button disabled={!rows.length} onClick={() => setCompare(true)}>
                Compare nearby payments
              </Button>
            </>
          )}
        </div>
      )}
      {compare && complete && (
        <PaymentComparison
          caseId={caseId}
          ids={rows.map((item) => item.key)}
          title={`Same account: ${startDate} to ${endDate}`}
          onClose={() => setCompare(false)}
        />
      )}
    </section>
  )
}
