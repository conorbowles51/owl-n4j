import type { LedgerTransaction } from "../api"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"
import { paymentDay } from "./investigator-workspace"

/** The payment a trace starts from, carried from Follow money into Trace funds. */
export interface TraceStart {
  key: string
  account_id: string
  account_label: string
  payer: string
  day: string
  end: string
  amount_minor: string
  currency: string
  population: "working" | "verified"
  /** Set on each click, so the same payment clicked again loads again. */
  at: number
}

export const TRACE_START_DRAFT = "trace-start"

function day(row: LedgerTransaction) {
  return paymentDay(row) || row.ordering_date?.slice(0, 10) || ""
}

/**
 * The trace of one clicked payment: its account, from its day to the end of the dates Follow money shows (the
 * chosen end date, or the last payment's day when no end date is chosen), over the payments Follow money shows.
 */
export function traceStartFrom(
  row: LedgerTransaction,
  rows: LedgerTransaction[],
  scope: LedgerQueryParams
): TraceStart {
  const start = day(row)
  let end = scope.endDate || ""
  if (!end) for (const r of rows) if (day(r) > end) end = day(r)
  return {
    key: row.key,
    account_id: row.account_id,
    account_label: row.account_label || "Account",
    payer:
      row.from_name ||
      row.counterparty_raw ||
      row.description ||
      "Payer not recorded",
    day: start,
    end: end < start ? start : end,
    amount_minor: String(row.amount_minor),
    currency: row.currency,
    // Follow money shows every admitted payment, verified or not: the trace reads the same ones ("All imported
    // payments"). Tracing verified payments only stays one choice away in the form.
    population: "working",
    at: Date.now(),
  }
}

/** Fills the Trace funds form with the clicked payment's account and dates, so the trace opens on it. */
export function writeTraceStart(caseId: string, start: TraceStart) {
  const put = useFinancialDraftStore.getState().put
  const key = (name: string) => financialDraftKey(caseId, name)
  put(key("tracing-mode"), "single")
  put(key("single-trace-filter"), {
    search: "",
    account: { id: start.account_id, label: start.account_label },
    start: start.day,
    end: start.end,
  })
  put(key("single-trace-scope"), {
    accountId: start.account_id,
    startDate: start.day,
    endDate: start.end,
  } satisfies LedgerQueryParams)
  put(key("single-trace-population"), start.population)
  put(key(TRACE_START_DRAFT), start)
}

/** Payments out of the start's account on or after its day, up to the end day, in date order (the first step). */
export function onwardPayments(rows: LedgerTransaction[], start: TraceStart) {
  return rows
    .filter(
      (r) =>
        r.key !== start.key &&
        r.account_id === start.account_id &&
        r.currency === start.currency &&
        r.direction === "debit" &&
        day(r) >= start.day &&
        day(r) <= start.end
    )
    .sort(
      (a, b) =>
        (a.ordering_date || "").localeCompare(b.ordering_date || "") ||
        a.key.localeCompare(b.key)
    )
}

/** How many onward payments, in order, it takes for their total to reach the amount that came in (null: never). */
export function paymentsCovering(
  onward: LedgerTransaction[],
  amountMinor: string
) {
  let total = 0n
  const target = BigInt(amountMinor)
  for (let i = 0; i < onward.length; i++) {
    total += BigInt(onward[i].amount_minor)
    if (total >= target) return i + 1
  }
  return null
}
