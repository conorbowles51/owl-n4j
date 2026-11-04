/**
 * The Trends page from the server's answer (`/ledger-trends-view`): the same figures investigateTrends,
 * changeDrivers and trendObservations work out from every payment, with the payments behind each figure as keys, so
 * the page shows them without downloading every payment (d5b330d1: 64 MB). Sorting and statement coverage are done
 * here with the browser's own functions.
 */
import {
  coverageFor,
  sortDrivers,
  sortGroups,
  sortObservations,
  type ChangeDriver,
  type CoverageInput,
  type DateRange,
  type TrendObservation,
} from "./investigation-trends"

/** A payment the page refers to by key only (it opens the payments behind a figure by their keys). */
export interface TrendRow {
  key: string
}
export type TrendViewObservation = Omit<TrendObservation, "rows" | "earlierRows"> & {
  rows: TrendRow[]
  earlierRows: TrendRow[]
}
export type TrendViewDriver = Omit<ChangeDriver, "earlier" | "later"> & {
  earlier: TrendRow[]
  later: TrendRow[]
}
interface ServerDriver {
  key: string
  name: string
  suggested: boolean
  unknown: boolean
  earlier: string[]
  later: string[]
  before: string
  after: string
  delta: string
}
interface ServerObservation {
  id: string
  kind: TrendObservation["kind"]
  title: string
  explanation: string
  amount: string
  rows: string[]
  earlier_rows: string | null
  suggested: boolean
  direction: string
  baseline?: { median_twice: string; maximum: string; count: number }
}
export interface TrendsServerView {
  case_id: string
  available: boolean
  reason?: string
  complete?: boolean
  groups?: { group: string; count: number }[]
  group?: string
  earlier?: DateRange
  later?: DateRange
  scoped_count?: number
  scoped_dated?: boolean
  error?: string | null
  result?: {
    accounts: { id: string; label: string; aliasIds?: string[] }[]
    before_count: number
    after_count: number
    unknown_dates: string[]
    invalid_amounts: number
    history_count: number
    totals: {
      direction: "credit" | "debit"
      before: string
      after: string
      beforeCount: number
      afterCount: number
    }[]
    drivers: Record<string, ServerDriver[]>
    observations: ServerObservation[]
    baselines: Record<string, string[]>
  } | null
}

const rowsOf = (keys: string[]): TrendRow[] => keys.map((key) => ({ key }))

/** The groups in the page's order (most payments first, then by name). */
export const serverGroups = (view: TrendsServerView) =>
  sortGroups((view.groups ?? []).map((g) => [g.group, g.count]))

/** The figures investigateTrends returns, from the server's answer, with coverage worked out here. */
export function trendsFromServer(view: TrendsServerView, input: CoverageInput) {
  const r = view.result
  if (!r || !view.earlier || !view.later) return null
  const coverage = {
    earlier: coverageFor(view.earlier, r.accounts, input),
    later: coverageFor(view.later, r.accounts, input),
  }
  const observations: TrendViewObservation[] = sortObservations(
    r.observations.map((o) => ({
      id: o.id,
      kind: o.kind,
      title: o.title,
      explanation: o.explanation,
      amount: BigInt(o.amount),
      rows: rowsOf(o.rows),
      earlierRows: o.earlier_rows ? rowsOf(r.baselines[o.earlier_rows] ?? []) : [],
      suggested: o.suggested,
      direction: o.direction,
      ...(o.baseline
        ? {
            baseline: {
              medianTwice: BigInt(o.baseline.median_twice),
              maximum: BigInt(o.baseline.maximum),
              count: o.baseline.count,
            },
          }
        : {}),
    }))
  )
  return {
    earlier: view.earlier,
    later: view.later,
    group: view.group ?? "",
    accounts: r.accounts,
    coverage,
    unknownDates: rowsOf(r.unknown_dates),
    invalidAmountCount: r.invalid_amounts,
    comparable:
      coverage.earlier.full &&
      coverage.later.full &&
      !r.unknown_dates.length &&
      !r.invalid_amounts,
    historyCount: r.history_count,
    observations,
    totals: r.totals.map((t) => ({
      ...t,
      before: BigInt(t.before),
      after: BigInt(t.after),
    })),
  }
}

/** changeDrivers' answer for one direction and grouping, from the server's answer. */
export function driversFromServer(
  view: TrendsServerView,
  direction: string,
  by: "name" | "category"
): TrendViewDriver[] {
  return sortDrivers(
    (view.result?.drivers[`${direction}:${by}`] ?? []).map((d) => ({
      ...d,
      earlier: rowsOf(d.earlier),
      later: rowsOf(d.later),
      before: BigInt(d.before),
      after: BigInt(d.after),
      delta: BigInt(d.delta),
    }))
  )
}
