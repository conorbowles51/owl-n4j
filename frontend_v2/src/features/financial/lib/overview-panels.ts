/**
 * The Overview's lower panels from the server (GET /api/financial/ledger-overview-panels): payment totals per
 * currency and account type, who paid in and where payments went, and money in then out within a week, worked out
 * over exactly the rows the ledger answers (services/financial/overview_panels.py), so the Overview does not
 * download every payment to draw them. The server returns its lists in the order it first meets them; the page
 * orders them here, with the same text order it always used (sort(), localeCompare).
 */
import type { LedgerTransaction } from "../api"
import { minorAmount, paymentGroup, paymentProfiles } from "./investigator-workspace"
import { unidentifiedGroups, unidentifiedPayment } from "./unidentified-payments"
import { yieldToBrowser } from "@/lib/sliced-json"

/** A sum in minor units as text, or null where the page says "Amount needs checking". */
export type PanelTotal = string | null

export interface PanelSide {
  keys: string[]
  total: PanelTotal
  /** Some names were suggested from the payment descriptions. */
  suggested: boolean
}

export interface PanelGroup {
  /** "<currency>:bank" or "<currency>:card" */
  group: string
  credit_total: PanelTotal
  debit_total: PanelTotal
  names: { id: string; name: string; credit: PanelSide; debit: PanelSide }[]
  accounts: { id: string; name: string; keys: string[] }[]
  unnamed: {
    direction: string
    kind: string
    label: string
    reason: string
    keys: string[]
    total: PanelTotal
  }[]
}

export interface OverviewPanels {
  case_id: string
  complete: boolean
  categories: string[]
  totals: {
    payments: number
    inventory: {
      accounts: { id: string; label: string; currencies: string[] }[]
      banks: string[]
      currencies: string[]
      first: string | null
      last: string | null
      undated: number
      unknown_banks: number
      unidentified_counterparties: number
    }
    groups: { group: string; credit: string; debit: string; count: number; accounts: number }[]
    unreadable: number
  }
  connections: { payments: number; groups: PanelGroup[] }
  comparisons: { pairs: number; keys: string[] }
}

/** The panels as the page shows them: inventory accounts, banks, currencies and connection groups in the page's
 * own order (the same calls the page made over every payment). */
export function orderOverviewPanels(panels: OverviewPanels): OverviewPanels {
  const inventory = panels.totals.inventory
  return {
    ...panels,
    totals: {
      ...panels.totals,
      inventory: {
        ...inventory,
        accounts: [...inventory.accounts].sort((a, b) => a.label.localeCompare(b.label)),
        banks: [...inventory.banks].sort(),
        currencies: [...inventory.currencies].sort(),
      },
    },
    connections: {
      ...panels.connections,
      groups: [...panels.connections.groups].sort((a, b) => (a.group < b.group ? -1 : a.group > b.group ? 1 : 0)),
    },
  }
}

const sumOf = (payments: LedgerTransaction[]): PanelTotal => {
  const amounts = payments.map((row) => minorAmount(row.amount_minor))
  if (amounts.some((value) => value === null)) return null
  return amounts.reduce<bigint>((sum, value) => sum + value!, 0n).toString()
}

/** The connections panel's figures for every currency and account type in `rows`, in the page's order: the same
 * calculation the server makes (services/financial/overview_panels.py money_connections), for pages that already
 * hold every payment. */
export function connectionGroups(rows: LedgerTransaction[]): PanelGroup[] {
  const steps = connectionSteps(rows)
  for (;;) {
    const next = steps.next()
    if (next.done) return next.value
  }
}

/** Steps done of steps in all, for the page's status line while it groups. */
export type GroupingProgress = (done: number, total: number) => void

/**
 * connectionGroups in steps (each person/account list, then each currency group), giving the browser a turn whenever
 * a step has run past BUDGET_MS so the page keeps redrawing: on d5b330d1 (27,673 payments) the whole calculation held
 * the main thread 0.6 s on an idle host and 1.2-1.6 s on a busy one (live long-task trace, 2026-11-01). The value is
 * the one connectionGroups gives: both run connectionSteps. `signal.cancelled` stops it early (a newer row list).
 */
export async function connectionGroupsInSteps(
  rows: LedgerTransaction[],
  progress?: GroupingProgress,
  signal?: { cancelled: boolean }
): Promise<PanelGroup[] | null> {
  const steps = connectionSteps(rows)
  let since = performance.now()
  for (;;) {
    const next = steps.next()
    if (next.done) return next.value
    if (signal?.cancelled) return null
    if (performance.now() - since > BUDGET_MS) {
      progress?.(next.value.done, next.value.total)
      await yieldToBrowser()
      if (signal?.cancelled) return null
      since = performance.now()
    }
  }
}

const BUDGET_MS = 25

function* connectionSteps(rows: LedgerTransaction[]): Generator<{ done: number; total: number }, PanelGroup[]> {
  // Each row's currency and account type, worked out once (paymentGroup is a pure function of the row).
  const groupOf = new Map<LedgerTransaction, string>()
  const group = (row: LedgerTransaction) => {
    let value = groupOf.get(row)
    if (value === undefined) {
      value = paymentGroup(row)
      groupOf.set(row, value)
    }
    return value
  }
  for (const row of rows) group(row)
  const order = [...new Set(rows.map(group))].sort()
  const total = order.length + 2
  const names = paymentProfiles(rows.filter((row) => !unidentifiedPayment(row))).filter(
    (profile) => profile.kind === "name"
  )
  yield { done: 1, total }
  const accounts = paymentProfiles(rows).filter((profile) => profile.kind === "account")
  yield { done: 2, total }
  const side = (payments: LedgerTransaction[], field: "from_name" | "to_name"): PanelSide => ({
    keys: payments.map((row) => row.key),
    total: sumOf(payments),
    suggested: payments.some((row) => row.label_sources?.[field]?.source === "description"),
  })
  const result: PanelGroup[] = []
  for (const name of order) {
    const members = rows.filter((row) => group(row) === name)
    result.push({
      group: name,
      credit_total: sumOf(members.filter((row) => row.direction === "credit")),
      debit_total: sumOf(members.filter((row) => row.direction === "debit")),
      names: names
        .filter((profile) => profile.rows.some((row) => group(row) === name))
        .map((profile) => {
          const mine = profile.rows.filter((row) => group(row) === name)
          return {
            id: profile.id,
            name: profile.name,
            credit: side(mine.filter((row) => row.direction === "credit"), "from_name"),
            debit: side(mine.filter((row) => row.direction === "debit"), "to_name"),
          }
        }),
      accounts: accounts
        .filter((profile) => profile.rows.some((row) => group(row) === name))
        .map((profile) => ({
          id: profile.id,
          name: profile.name,
          keys: profile.rows.filter((row) => group(row) === name).map((row) => row.key),
        })),
      unnamed: unidentifiedGroups(members).map((item) => ({
        direction: item.direction,
        kind: item.kind,
        label: item.label,
        reason: item.reason,
        keys: item.rows.map((row) => row.key),
        total: sumOf(item.rows),
      })),
    })
    yield { done: result.length + 2, total }
  }
  return result
}

/**
 * Why grouping failed, in plain words. The browser's own text for running out of room ("Maximum call stack size
 * exceeded", "out of memory", "Allocation failed") is technical; it stays in brackets so the cause is not hidden.
 */
export function groupingFailureWords(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error)
  if (error instanceof RangeError || /call stack|out of memory|allocation failed/i.test(raw))
    return `the browser ran out of working space for this many payments (it said: ${raw})`
  return raw
}
