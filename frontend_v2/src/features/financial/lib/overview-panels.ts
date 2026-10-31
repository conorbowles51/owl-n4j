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
  const names = paymentProfiles(rows.filter((row) => !unidentifiedPayment(row))).filter(
    (profile) => profile.kind === "name"
  )
  const accounts = paymentProfiles(rows).filter((profile) => profile.kind === "account")
  const side = (payments: LedgerTransaction[], field: "from_name" | "to_name"): PanelSide => ({
    keys: payments.map((row) => row.key),
    total: sumOf(payments),
    suggested: payments.some((row) => row.label_sources?.[field]?.source === "description"),
  })
  return [...new Set(rows.map(paymentGroup))].sort().map((group) => {
    const members = rows.filter((row) => paymentGroup(row) === group)
    return {
      group,
      credit_total: sumOf(members.filter((row) => row.direction === "credit")),
      debit_total: sumOf(members.filter((row) => row.direction === "debit")),
      names: names
        .filter((profile) => profile.rows.some((row) => paymentGroup(row) === group))
        .map((profile) => {
          const mine = profile.rows.filter((row) => paymentGroup(row) === group)
          return {
            id: profile.id,
            name: profile.name,
            credit: side(mine.filter((row) => row.direction === "credit"), "from_name"),
            debit: side(mine.filter((row) => row.direction === "debit"), "to_name"),
          }
        }),
      accounts: accounts
        .filter((profile) => profile.rows.some((row) => paymentGroup(row) === group))
        .map((profile) => ({
          id: profile.id,
          name: profile.name,
          keys: profile.rows.filter((row) => paymentGroup(row) === group).map((row) => row.key),
        })),
      unnamed: unidentifiedGroups(members).map((item) => ({
        direction: item.direction,
        kind: item.kind,
        label: item.label,
        reason: item.reason,
        keys: item.rows.map((row) => row.key),
        total: sumOf(item.rows),
      })),
    }
  })
}
