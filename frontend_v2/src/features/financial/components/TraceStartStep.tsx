import { useMemo, useState } from "react"
import { useElapsedSeconds } from "../hooks/use-elapsed-seconds"
import { Button } from "@/components/ui/button"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useFinancialDraft } from "../stores/financial-drafts"
import { formatLedgerAmount } from "../lib/ledger-format"
import { paymentDay } from "../lib/investigator-workspace"
import {
  TRACE_START_DRAFT,
  onwardPayments,
  paymentsCovering,
  type TraceStart,
} from "../lib/trace-start"

const SHOWN = 25

/**
 * The first step of a trace started from a payment in Follow money: the payments out of its account on or after
 * the day it came in, read from the payments Follow money already holds (no new request), in date order.
 */
export function TraceStartStep({ caseId }: { caseId: string }) {
  const [start, , clear] = useFinancialDraft<TraceStart | null>(
    caseId,
    TRACE_START_DRAFT,
    null
  )
  if (!start) return null
  return <StartStep key={start.at} caseId={caseId} start={start} clear={clear} />
}

function StartStep({
  caseId,
  start,
  clear,
}: {
  caseId: string
  start: TraceStart
  clear: () => void
}) {
  const data = useInvestigatorPayments(caseId)
  const [opened] = useState(() => Date.now())
  const [showAll, setShowAll] = useState(false)
  const reading =
    !data.complete &&
    !data.query.isError &&
    (data.query.isPending || data.query.isFetching)
  const incomplete = !data.complete && !data.query.isError && !reading
  const seconds = useElapsedSeconds(reading, opened)
  const all = data.complete ? data.query.data!.transactions : null
  const onward = useMemo(
    () => (all ? onwardPayments(all, start) : []),
    [all, start]
  )
  const money = (minor: string | number | bigint) =>
    `${formatLedgerAmount(String(minor), start.currency).text} ${start.currency}`
  const total = onward.reduce((sum, r) => sum + BigInt(r.amount_minor), 0n)
  const covering = paymentsCovering(onward, start.amount_minor)
  const shown = showAll ? onward : onward.slice(0, SHOWN)
  return (
    <section
      aria-label="Where it went next"
      className="space-y-3 rounded border border-[#b41624] p-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">Where it went next</h3>
          <p>
            Traced from {money(start.amount_minor)} in from {start.payer} on{" "}
            {start.day}, into {start.account_label}.
          </p>
        </div>
        <Button variant="outline" onClick={clear}>
          Clear this start
        </Button>
      </div>
      {reading && (
        <p role="status">
          Reading this case's payments to find what left {start.account_label}{" "}
          after {start.day}… {seconds} s
        </p>
      )}
      {data.query.isError && (
        <div role="alert" className="space-y-2">
          <p>
            The payments could not be read, so where it went next is not
            known yet:{" "}
            {data.query.error instanceof Error
              ? data.query.error.message
              : "the request failed"}
            .
          </p>
          <Button onClick={() => void data.query.refetch()}>Retry</Button>
        </div>
      )}
      {incomplete && (
        <div role="alert" className="space-y-2">
          <p>
            The payments read back were not the whole case, so where it went
            next is not shown. Read them again.
          </p>
          <Button onClick={() => void data.query.refetch()}>Retry</Button>
        </div>
      )}
      {all && onward.length === 0 && (
        <p role="status">
          No payments out of {start.account_label} from {start.day} to{" "}
          {start.end} in the statements loaded. If money left later, its
          statement is not in the case yet: check Statements &amp; accounts for a
          missing period of this account, or widen the dates in Follow money and
          trace again.
        </p>
      )}
      {all && onward.length > 0 && (
        <>
          <p role="status">
            {onward.length.toLocaleString()} payment
            {onward.length === 1 ? "" : "s"} out of {start.account_label} from{" "}
            {start.day} to {start.end}, {money(total)} in total.{" "}
            {covering === null
              ? `Together they are less than the ${money(start.amount_minor)} that came in.`
              : `The first ${covering.toLocaleString()} of them, in date order, add up to the ${money(start.amount_minor)} that came in.`}{" "}
            Other money in the account mixes with it; choose a tracing rule
            below to allocate it.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left">
                <th>Date</th>
                <th>To</th>
                <th className="text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.key}>
                  <td className="tabular-nums">
                    {paymentDay(row) || row.ordering_date?.slice(0, 10)}
                  </td>
                  <td>
                    {row.to_name ||
                      row.counterparty_raw ||
                      row.description ||
                      "Payee not recorded"}
                  </td>
                  <td className="text-right tabular-nums">
                    {money(row.amount_minor)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {onward.length > SHOWN && (
            <p>
              Showing {shown.length.toLocaleString()} of{" "}
              {onward.length.toLocaleString()}.{" "}
              <Button variant="outline" onClick={() => setShowAll(!showAll)}>
                {showAll ? `Show the first ${SHOWN}` : "Show all"}
              </Button>
            </p>
          )}
        </>
      )}
    </section>
  )
}
