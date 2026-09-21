import type { LedgerTransaction } from "../api"
import { minorAmount, paymentDay, paymentGroup } from "./investigator-workspace"
import { party } from "./transaction-analysis"

export const TREND_RULES = {
  version: "investigation-trends/1",
  recurringMinimum: 3,
  weeklyGapDays: [5, 9],
  monthlyGapDays: [25, 35],
  largePaymentMultiple: 3,
  earlierMinimum: 5,
  returnMaximumDays: 7,
} as const
export interface DateRange {
  start: string
  end: string
}
export interface CoveragePeriod {
  account_id: string
  account_label: string
  start: string | null
  end: string | null
  source_status: string
  incomplete?: boolean
}
export interface CoverageInput {
  available: boolean
  truncated: boolean
  periods: CoveragePeriod[]
}
const DAY = 86400000
const stamp = (day: string) => Date.parse(`${day}T00:00:00Z`)
export const dateValid = (value: string) =>
  /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(stamp(value)) &&
  new Date(stamp(value)).toISOString().slice(0, 10) === value
export const daysIn = (range: DateRange) =>
  Math.round((stamp(range.end) - stamp(range.start)) / DAY) + 1
export const withinRange = (row: LedgerTransaction, range: DateRange) => {
  const date = paymentDay(row)
  return !!date && date >= range.start && date <= range.end
}
export function monthRange(month: string): DateRange {
  if (!/^\d{4}-\d{2}$/.test(month) || !dateValid(`${month}-01`))
    return { start: "", end: "" }
  const next = new Date(`${month}-01T00:00:00Z`)
  next.setUTCMonth(next.getUTCMonth() + 1)
  next.setUTCDate(0)
  return { start: `${month}-01`, end: next.toISOString().slice(0, 10) }
}
export function defaultTrendRanges(rows: LedgerTransaction[]) {
  const last = rows
    .flatMap((row) => (paymentDay(row) ? [paymentDay(row)!] : []))
    .sort()
    .at(-1)
  if (!last)
    return { earlier: { start: "", end: "" }, later: { start: "", end: "" } }
  const later = monthRange(last.slice(0, 7)),
    prev = new Date(stamp(later.start))
  prev.setUTCMonth(prev.getUTCMonth() - 1)
  return { earlier: monthRange(prev.toISOString().slice(0, 7)), later }
}
export function rangeError(earlier: DateRange, later: DateRange) {
  if (![earlier.start, earlier.end, later.start, later.end].every(dateValid))
    return "Choose valid start and end dates for both periods."
  if (earlier.start > earlier.end || later.start > later.end)
    return "Each period must end on or after its start date."
  if (earlier.end >= later.start)
    return "The earlier period must finish before the later period starts; comparison periods cannot overlap."
  return null
}
export function coverageFor(
  range: DateRange,
  accounts: { id: string; label: string }[],
  input: CoverageInput
) {
  const details = accounts.map((account) => {
    const spans = input.periods
      .filter(
        (p) =>
          p.account_id === account.id &&
          p.source_status === "admitted" &&
          p.start &&
          p.end &&
          dateValid(p.start) &&
          dateValid(p.end) &&
          p.start <= p.end &&
          p.start <= range.end &&
          p.end >= range.start
      )
      .map((p) => ({
        start: Math.max(stamp(p.start!), stamp(range.start)),
        end: Math.min(stamp(p.end!), stamp(range.end)),
        incomplete: p.incomplete,
      }))
      .sort((a, b) => a.start - b.start)
    const merged: { start: number; end: number }[] = []
    for (const span of spans) {
      const last = merged.at(-1)
      if (last && span.start <= last.end + DAY)
        last.end = Math.max(last.end, span.end)
      else merged.push({ start: span.start, end: span.end })
    }
    const coveredDays = merged.reduce(
      (sum, s) => sum + Math.round((s.end - s.start) / DAY) + 1,
      0
    )
    return {
      ...account,
      coveredDays,
      totalDays: daysIn(range),
      incomplete: spans.some((s) => s.incomplete),
      full: coveredDays === daysIn(range),
    }
  })
  return {
    details,
    full:
      input.available &&
      !input.truncated &&
      details.length > 0 &&
      details.every((d) => d.full && !d.incomplete),
    available: input.available,
    truncated: input.truncated,
  }
}
export function trendAmount(row: LedgerTransaction) {
  const value = minorAmount(row.amount_minor)
  return value !== null &&
    value >= 0n &&
    (row.direction === "credit" || row.direction === "debit")
    ? value
    : null
}
export const sumPayments = (rows: LedgerTransaction[]) =>
  rows.reduce((sum, row) => sum + (trendAmount(row) ?? 0n), 0n)
const absolute = (n: bigint) => (n < 0n ? -n : n)
const bigintCompare = (a: bigint, b: bigint) => (a === b ? 0 : a > b ? 1 : -1)
export function changePercent(earlier: bigint, later: bigint) {
  if (!earlier) return null
  const difference = later - earlier
  const tenths = (absolute(difference) * 1000n + earlier / 2n) / earlier
  return `${difference > 0n ? "+" : difference < 0n ? "−" : ""}${tenths / 10n}.${tenths % 10n}%`
}
export interface ChangeDriver {
  key: string
  name: string
  suggested: boolean
  unknown: boolean
  earlier: LedgerTransaction[]
  later: LedgerTransaction[]
  before: bigint
  after: bigint
  delta: bigint
}
export function changeDrivers(
  earlier: LedgerTransaction[],
  later: LedgerTransaction[],
  direction: string,
  by: "name" | "category"
): ChangeDriver[] {
  const groups = new Map<string, ChangeDriver>()
  for (const [side, rows] of [
    ["earlier", earlier],
    ["later", later],
  ] as const)
    for (const row of rows) {
      if (row.direction !== direction || trendAmount(row) === null) continue
      const p = party(row, direction === "credit" ? "from" : "to")
      const name =
        by === "category"
          ? row.category || "Uncategorized"
          : p.key.startsWith("unknown:")
            ? "Counterparty not identified"
            : p.name
      const key = by === "category" ? name : p.key
      const group = groups.get(key) ?? {
        key,
        name,
        suggested: false,
        unknown: p.key.startsWith("unknown:"),
        earlier: [],
        later: [],
        before: 0n,
        after: 0n,
        delta: 0n,
      }
      group[side].push(row)
      group.suggested ||=
        by === "category"
          ? row.label_sources?.category?.source === "description"
          : p.suggested
      if (side === "earlier") group.before += trendAmount(row)!
      else group.after += trendAmount(row)!
      group.delta = group.after - group.before
      groups.set(key, group)
    }
  return [...groups.values()].sort(
    (a, b) =>
      bigintCompare(absolute(b.delta), absolute(a.delta)) ||
      a.name.localeCompare(b.name)
  )
}
export interface TrendObservation {
  id: string
  kind: "first-seen" | "recurring" | "larger" | "return"
  title: string
  explanation: string
  amount: bigint
  rows: LedgerTransaction[]
  earlierRows: LedgerTransaction[]
  suggested: boolean
  direction: string
  baseline?: { medianTwice: bigint; maximum: bigint; count: number }
}
function ref(row: LedgerTransaction) {
  return (
    row.bank_reference?.trim() ||
    /\bRef\s*[.:]\s*([\w.-]+)/i.exec(row.description || "")?.[1] ||
    ""
  )
}
function appendPayment(
  map: Map<string, LedgerTransaction[]>,
  key: string,
  row: LedgerTransaction
) {
  const list = map.get(key)
  if (list) list.push(row)
  else map.set(key, [row])
}
const referenceKey = (row: LedgerTransaction) =>
  JSON.stringify([
    row.account_id,
    paymentGroup(row),
    trendAmount(row)?.toString(),
    ref(row),
  ])
export function trendObservations(
  rows: LedgerTransaction[],
  earlier: DateRange,
  later: DateRange
): TrendObservation[] {
  const dated = rows.filter((r) => paymentDay(r) && trendAmount(r) !== null)
  const current = dated.filter((r) => withinRange(r, later)),
    previous = dated.filter((r) => withinRange(r, earlier))
  const history = dated.filter((r) => paymentDay(r)! < later.start)
  const result: TrendObservation[] = []
  if (history.length) {
    const seen = new Set(
      history.map((r) => party(r, r.direction === "credit" ? "from" : "to").key)
    )
    const first = new Map<string, LedgerTransaction[]>()
    for (const row of current) {
      const p = party(row, row.direction === "credit" ? "from" : "to")
      if (p.key.startsWith("unknown:") || seen.has(p.key)) continue
      const key = `${row.direction}:${p.key}`
      appendPayment(first, key, row)
    }
    for (const [key, payments] of first) {
      const p = party(
        payments[0],
        payments[0].direction === "credit" ? "from" : "to"
      )
      const start = payments.map((r) => paymentDay(r)!).sort()[0]
      result.push({
        id: `first:${key}`,
        kind: "first-seen",
        title: p.name,
        explanation: `First appears on ${start} in the loaded records for this scope; ${payments.length} later-period payments. Earlier loaded records contain no payment with this displayed name. This does not establish a new relationship.`,
        amount: sumPayments(payments),
        rows: payments,
        earlierRows: [],
        suggested: payments.some(
          (r) => party(r, r.direction === "credit" ? "from" : "to").suggested
        ),
        direction: payments[0].direction,
      })
    }
  }
  const repeated = new Map<string, LedgerTransaction[]>()
  for (const row of dated.filter((r) => paymentDay(r)! <= later.end)) {
    const p = party(row, row.direction === "credit" ? "from" : "to")
    if (p.key.startsWith("unknown:")) continue
    const key = JSON.stringify([
      row.account_id,
      paymentGroup(row),
      row.direction,
      p.key,
      trendAmount(row)!.toString(),
    ])
    appendPayment(repeated, key, row)
  }
  for (const [key, payments] of repeated) {
    if (
      payments.length < TREND_RULES.recurringMinimum ||
      !payments.some((r) => withinRange(r, later))
    )
      continue
    payments.sort((a, b) => paymentDay(a)!.localeCompare(paymentDay(b)!))
    const gaps = payments
      .slice(1)
      .map(
        (r, i) =>
          (stamp(paymentDay(r)!) - stamp(paymentDay(payments[i])!)) / DAY
      )
    const cadence = gaps.every(
      (g) =>
        g >= TREND_RULES.weeklyGapDays[0] && g <= TREND_RULES.weeklyGapDays[1]
    )
      ? "Weekly"
      : gaps.every(
            (g) =>
              g >= TREND_RULES.monthlyGapDays[0] &&
              g <= TREND_RULES.monthlyGapDays[1]
          )
        ? "Monthly"
        : ""
    if (!cadence) continue
    const p = party(
      payments[0],
      payments[0].direction === "credit" ? "from" : "to"
    )
    result.push({
      id: `recurring:${key}`,
      kind: "recurring",
      title: `${cadence} payments · ${p.name}`,
      explanation: `${payments.length} payments of the same amount in ${payments[0].account_label || "one account"}, ${paymentDay(payments[0])} to ${paymentDay(payments.at(-1)!)}. Gaps are ${Math.min(...gaps)}–${Math.max(...gaps)} days. This is an observed schedule, not proof of a contract or purpose.`,
      amount: trendAmount(payments[0])!,
      rows: payments,
      earlierRows: [],
      suggested: payments.some(
        (r) => party(r, r.direction === "credit" ? "from" : "to").suggested
      ),
      direction: payments[0].direction,
    })
  }
  const baselines = new Map<string, LedgerTransaction[]>()
  for (const row of previous) {
    const key = `${row.account_id}:${row.direction}`
    appendPayment(baselines, key, row)
  }
  for (const [key, baseline] of baselines) {
    if (baseline.length < TREND_RULES.earlierMinimum) continue
    const sorted = baseline.map((r) => trendAmount(r)!).sort(bigintCompare)
    // Twice the median keeps even-sized samples exact, without rounding money.
    const medianTwice =
      sorted.length % 2
        ? sorted[Math.floor(sorted.length / 2)] * 2n
        : sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]
    if (!medianTwice) continue
    for (const row of current.filter(
      (r) => `${r.account_id}:${r.direction}` === key
    )) {
      const value = trendAmount(row)!
      if (
        value * 2n <= medianTwice * BigInt(TREND_RULES.largePaymentMultiple) ||
        value <= sorted.at(-1)!
      )
        continue
      result.push({
        id: `larger:${row.key}`,
        kind: "larger",
        title: row.description || "Larger payment",
        explanation: `Above every one of the ${baseline.length} earlier payments in the same account and direction, and more than three times their median. Compare the earlier payments before interpreting this increase.`,
        amount: value,
        rows: [row],
        earlierRows: baseline,
        suggested: false,
        direction: row.direction,
        baseline: {
          medianTwice,
          maximum: sorted.at(-1)!,
          count: baseline.length,
        },
      })
    }
  }
  const outgoing = new Map<string, LedgerTransaction[]>()
  const returned = new Map<string, LedgerTransaction[]>()
  for (const row of dated) {
    const reference = ref(row)
    if (reference) {
      if (row.direction === "debit")
        appendPayment(outgoing, referenceKey(row), row)
      else if (/\b(?:SPEI|SPID)\s+DEVUELTO/i.test(row.description || ""))
        appendPayment(returned, referenceKey(row), row)
    }
  }
  for (const row of current.filter(
    (r) =>
      r.direction === "credit" &&
      /\b(?:SPEI|SPID)\s+DEVUELTO/i.test(r.description || "")
  )) {
    const reference = ref(row)
    if (!reference) continue
    const matches = (outgoing.get(referenceKey(row)) ?? []).filter((p) => {
      const gap = (stamp(paymentDay(row)!) - stamp(paymentDay(p)!)) / DAY
      return (
        gap >= 0 &&
        gap <= TREND_RULES.returnMaximumDays &&
        (gap > 0 ||
          (p.source_document_id === row.source_document_id &&
            p.statement_period_id === row.statement_period_id &&
            p.row_index < row.row_index))
      )
    })
    if (matches.length !== 1) continue
    const credits = (returned.get(referenceKey(row)) ?? []).filter(
      (p) =>
        stamp(paymentDay(p)!) >= stamp(paymentDay(matches[0])!) &&
        stamp(paymentDay(p)!) <=
          stamp(paymentDay(matches[0])!) + TREND_RULES.returnMaximumDays * DAY
    )
    if (credits.length !== 1) continue
    result.push({
      id: `return:${row.key}`,
      kind: "return",
      title: `Returned transfer · reference ${reference}`,
      explanation: `A credit explicitly described as a returned transfer matches one earlier debit by account, currency, amount and reference within seven days. Both entries remain in gross totals; this credit is not presented as a new payer.`,
      amount: trendAmount(row)!,
      rows: [matches[0], row],
      earlierRows: [],
      suggested: false,
      direction: "credit",
    })
  }
  return result.sort(
    (a, b) => bigintCompare(b.amount, a.amount) || a.id.localeCompare(b.id)
  )
}
export function investigateTrends(
  rows: LedgerTransaction[],
  group: string,
  earlier: DateRange,
  later: DateRange,
  input: CoverageInput
) {
  const error = rangeError(earlier, later)
  if (error) throw Error(error)
  if (rows.some((row) => paymentGroup(row) !== group))
    throw Error("Choose one currency and account type for a comparison.")
  const accounts = [
    ...new Map(
      rows.map((r) => [
        r.account_id,
        {
          id: r.account_id,
          label: r.account_label || r.account_holder || r.account_id,
        },
      ])
    ).values(),
  ]
  const before = rows.filter(
      (r) => withinRange(r, earlier) && trendAmount(r) !== null
    ),
    after = rows.filter((r) => withinRange(r, later) && trendAmount(r) !== null)
  const coverage = {
    earlier: coverageFor(earlier, accounts, input),
    later: coverageFor(later, accounts, input),
  }
  const unknownDates = rows.filter((r) => !paymentDay(r)),
    invalidAmounts = rows.filter((r) => trendAmount(r) === null)
  return {
    earlier,
    later,
    group,
    accounts,
    before,
    after,
    coverage,
    unknownDates,
    invalidAmounts,
    comparable:
      coverage.earlier.full &&
      coverage.later.full &&
      !unknownDates.length &&
      !invalidAmounts.length,
    historyCount: rows.filter(
      (r) => paymentDay(r) && paymentDay(r)! < later.start
    ).length,
    observations: trendObservations(rows, earlier, later),
    totals: (["credit", "debit"] as const).map((direction) => ({
      direction,
      before: sumPayments(before.filter((r) => r.direction === direction)),
      after: sumPayments(after.filter((r) => r.direction === direction)),
      beforeCount: before.filter((r) => r.direction === direction).length,
      afterCount: after.filter((r) => r.direction === direction).length,
    })),
  }
}
