import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useMoneyTrails } from "../hooks/use-money-trails"
import { correctionMoney } from "../lib/correction-contract"
import { MoneyTrailReview, TransferBreakdown } from "./MoneyTrailReview"

export function ReviewedMoneyTrails({
  caseId,
  rows,
}: {
  caseId: string
  rows: LedgerTransaction[]
}) {
  const query = useMoneyTrails(caseId)
  const [limit, setLimit] = useState(10)
  const visible = new Set(rows.map((p) => p.key))
  const transfers =
    query.data?.trails.filter(
      (t) =>
        t.active &&
        t.kind === "transfer" &&
        t.details.payments.some((p) => visible.has(p.key))
    ) ?? []
  if (query.error)
    return (
      <p role="alert">
        Saved money trails could not be checked.{" "}
        <button className="underline" onClick={() => void query.refetch()}>
          Retry
        </button>
      </p>
    )
  if (!transfers.length) return null
  return (
    <section
      aria-label="Reviewed money trails"
      className="rounded-xl border bg-card p-5 space-y-4"
    >
      <h3 className="font-semibold text-lg">Reviewed money trails</h3>
      <p>
        These links were saved by an investigator. Bank-to-bank transfer entries
        describe one movement; any onward allocation is a separate
        interpretation.
      </p>
      {transfers.slice(0, limit).map((trail) => {
        const d = trail.details,
          principal = d.payments.filter(
            (p) =>
              !d.transfer_breakdown ||
              d.transfer_breakdown.entries.some(
                (part) =>
                  part.transaction_id === p.key &&
                  BigInt(part.principal_minor) > 0n
              )
          ),
          debits = principal.filter((p) => p.direction === "debit"),
          credits = principal.filter((p) => p.direction === "credit")
        const onward = query.data!.trails.filter(
          (t) =>
            t.active &&
            t.kind === "allocation" &&
            credits.some((p) => p.key === t.details.input.credit_id)
        )
        return (
          <article key={trail.id} className="rounded-lg border p-4 space-y-3">
            {trail.status !== "current" && (
              <p role="alert">
                Source changed — review this saved interpretation.
              </p>
            )}
            <div className="rounded border bg-accent/25 p-3 space-y-2">
              <p className="font-semibold">
                {d.internal_transfer
                  ? `Reviewed common holder: ${d.common_holders.map((p) => p.name).join(", ")}`
                  : "Ownership not established for both accounts"}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                {[debits, credits].map((entries, index) => (
                  <div
                    key={index}
                    className="min-w-0 flex-1 rounded border bg-background p-3 break-words"
                  >
                    <p>{index === 0 ? "From" : "To"}:</p>
                    {!entries.length && (
                      <p>Referenced account — statement missing</p>
                    )}
                    {entries.map((p) => (
                      <p key={p.key}>
                        {p.account_label} ·{" "}
                        {correctionMoney(
                          d.transfer_breakdown?.entries.find(
                            (part) => part.transaction_id === p.key
                          )?.principal_minor || p.amount_minor,
                          p.currency
                        )}{" "}
                        {index === 0 ? "sent" : "received"} · {p.ordering_date}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
              {d.implied_exchange_rate && (
                <p>
                  Exchange hypothesis · implied rate {d.implied_exchange_rate};
                  both original currencies retained.
                </p>
              )}
            </div>
            <TransferBreakdown details={d} />
            {onward.map((allocation) => (
              <div key={allocation.id} className="rounded border p-3 space-y-2">
                <p>
                  ↓ Investigator’s onward allocation{" "}
                  {allocation.status !== "current"
                    ? "— source changed, review required"
                    : ""}
                </p>
                {(
                  allocation.details.input.payments as {
                    transaction_id: string
                    amount_minor: string
                  }[]
                ).map((item) => {
                  const payment = allocation.details.payments.find(
                    (p) => p.key === item.transaction_id
                  )!
                  return (
                    <p key={payment.key}>
                      {correctionMoney(item.amount_minor, payment.currency)}{" "}
                      allocated to{" "}
                      {payment.to_name || payment.description || payment.ref_id}{" "}
                      · {payment.ordering_date}
                    </p>
                  )
                })}
                <p>{String(allocation.details.input.reason)}</p>
                <MoneyTrailReview
                  caseId={caseId}
                  trailId={allocation.id}
                  label="Open allocation and sources"
                />
              </div>
            ))}
            <p>{String(d.input.reason)}</p>
            <MoneyTrailReview
              caseId={caseId}
              trailId={trail.id}
              label="Open transfer and statements"
            />
          </article>
        )
      })}
      {transfers.length > limit && (
        <Button variant="outline" onClick={() => setLimit((n) => n + 10)}>
          Show 10 more of {transfers.length} trails
        </Button>
      )}
    </section>
  )
}
