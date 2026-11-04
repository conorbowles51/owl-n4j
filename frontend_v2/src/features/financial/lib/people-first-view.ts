/**
 * The People & businesses list of names and accounts as the page draws it: one card per profile.
 *
 * A card is worked out either from a profile the browser grouped from every payment (`profileCard`) or from the
 * server's answer for the same payments and directory (GET /ledger-people-view, `serverProfileCards`), the same
 * figures either way. The list draws from the server's answer, so the page does not wait for every payment
 * (d5b330d1: 27,673 payments, a 64 MB answer); opening a profile reads every payment and works it out as before.
 */
import type { PaymentProfile } from "./investigator-workspace"
import { minorAmount } from "./investigator-workspace"
import { paymentTotalsFigures } from "./payment-totals"
import type { PaymentGroupTotal } from "../components/InvestigationTransactionTable"
import { unidentifiedGroups } from "./unidentified-payments"
import type { paymentInventory } from "./payment-inventory"

/** What ProfileStatementSummary shows, without the payments or the statement periods themselves. */
export interface ProfileStatementFacts {
  kind: PaymentProfile["kind"]
  accountDetails: {
    currency: string | null
    institution: string | null
    number: string | null
    accountType: string | null
    registered: boolean
    /** The directory gave this account's statement periods (false: "unavailable"). */
    coverage: boolean
  }[]
  /** Source documents of the profile's payments and statement periods. */
  sources: number
  statementPeriods: number
  statementMissingDates: number
  statementFirst: string | null
  statementLast: string | null
}

export interface ProfileCardTotals {
  payments: number
  inventory: ReturnType<typeof paymentInventory>
  totals: ReadonlyMap<string, PaymentGroupTotal>
  unreadable: number
}

export interface ProfileCard extends ProfileStatementFacts {
  id: string
  name: string
  nestedUnderOwner: boolean
  unidentified: boolean
  payments: number
  counterpartyPayments: number
  accounts: number
  first: string | null
  last: string | null
  /** PaymentTotals over the profile's payments; null when it has none. */
  totals: ProfileCardTotals | null
  /** The page's "Largest total": every amount added, an unreadable one as zero. */
  amount: bigint
  /** UnidentifiedBreakdown's groups (by kind, first met; the card sorts by count). */
  unidentifiedGroups: { label: string; reason: string; count: number }[] | null
}

export function statementFacts(profile: PaymentProfile): ProfileStatementFacts {
  return {
    kind: profile.kind,
    accountDetails: profile.accountDetails.map((account) => ({
      currency: account.currency,
      institution: account.institution,
      number: account.number,
      accountType: account.accountType,
      registered: account.registered,
      coverage: account.statementPeriods !== undefined,
    })),
    sources: profile.sources.length,
    statementPeriods: profile.statementPeriods.length,
    statementMissingDates: profile.statementPeriods.filter((period) => !period.start || !period.end).length,
    statementFirst: profile.statementFirst,
    statementLast: profile.statementLast,
  }
}

/** UnidentifiedBreakdown's grouping: unidentifiedGroups merged by kind (first position, last label and reason). */
export function unidentifiedBreakdown(rows: PaymentProfile["rows"]) {
  const groups = new Map<string, { label: string; reason: string; count: number }>()
  for (const group of unidentifiedGroups(rows)) {
    const previous = groups.get(group.kind)
    groups.set(group.kind, {
      label: group.label,
      reason: group.reason,
      count: (previous?.count ?? 0) + group.rows.length,
    })
  }
  return [...groups.values()]
}

export function profileCard(profile: PaymentProfile): ProfileCard {
  return {
    ...statementFacts(profile),
    id: profile.id,
    name: profile.name,
    nestedUnderOwner: profile.nestedUnderOwner,
    unidentified: profile.unidentified,
    payments: profile.rows.length,
    counterpartyPayments: profile.counterpartyRows.length,
    accounts: profile.accounts.length,
    first: profile.first,
    last: profile.last,
    totals: profile.rows.length ? paymentTotalsFigures(profile.rows) : null,
    amount: profile.rows.reduce((sum, row) => sum + (minorAmount(row.amount_minor) ?? 0n), 0n),
    unidentifiedGroups: profile.unidentified ? unidentifiedBreakdown(profile.rows) : null,
  }
}

interface ServerTotals {
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

export interface ServerProfile {
  id: string
  name: string
  kind: PaymentProfile["kind"]
  nested_under_owner: boolean
  unidentified: boolean
  payments: number
  counterparty_payments: number
  accounts: number
  account_details: ProfileStatementFacts["accountDetails"]
  sources: number
  first: string | null
  last: string | null
  statement_periods: number
  statement_periods_missing_dates: number
  statement_first: string | null
  statement_last: string | null
  totals: ServerTotals | null
  amount: string
  unidentified_groups: { label: string; reason: string; count: number }[] | null
}

export type PeopleServerView =
  | { case_id: string; available: false; reason: string }
  | ({ case_id: string; available: true } & (
      | { complete: false }
      | {
          complete: true
          categories: string[]
          group: string
          row_count: number
          row_groups: string[]
          directory_groups: string[]
          profiles: ServerProfile[]
        }
    ))

/** PaymentTotals' figures from the server's: lists in the page's own order (paymentInventory sorts them). */
function serverTotals(figures: ServerTotals): ProfileCardTotals {
  const inventory = figures.inventory
  return {
    payments: figures.payments,
    inventory: {
      accounts: inventory.accounts
        .map((account) => ({ ...account, currencies: new Set(account.currencies) }))
        .sort((a, b) => a.label.localeCompare(b.label)),
      banks: [...inventory.banks].sort(),
      currencies: [...inventory.currencies].sort(),
      first: inventory.first,
      last: inventory.last,
      undated: inventory.undated,
      unknownBanks: inventory.unknown_banks,
      unidentifiedCounterparties: inventory.unidentified_counterparties,
    },
    totals: new Map(
      figures.groups.map((group) => [
        group.group,
        { credit: BigInt(group.credit), debit: BigInt(group.debit), count: group.count, accountCount: group.accounts },
      ])
    ),
    unreadable: figures.unreadable,
  }
}

export function serverProfileCards(profiles: ServerProfile[]): ProfileCard[] {
  return profiles.map((profile) => ({
    kind: profile.kind,
    accountDetails: profile.account_details,
    sources: profile.sources,
    statementPeriods: profile.statement_periods,
    statementMissingDates: profile.statement_periods_missing_dates,
    statementFirst: profile.statement_first,
    statementLast: profile.statement_last,
    id: profile.id,
    name: profile.name,
    nestedUnderOwner: profile.nested_under_owner,
    unidentified: profile.unidentified,
    payments: profile.payments,
    counterpartyPayments: profile.counterparty_payments,
    accounts: profile.accounts,
    first: profile.first,
    last: profile.last,
    totals: profile.totals && serverTotals(profile.totals),
    amount: BigInt(profile.amount),
    unidentifiedGroups: profile.unidentified_groups,
  }))
}
