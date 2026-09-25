import type { LedgerTransaction } from "../api"
import type { AccountParties } from "./account-parties"

export function paymentDay(row: LedgerTransaction): string | null {
  if (row.ordering_date_context === "statement_end_ordering_only") return null
  const date = row.ordering_date?.slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || "")) return null
  const parsed = new Date(`${date}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === date
    ? date
    : null
}

export function minorAmount(value: string | number | null): bigint | null {
  if (
    value === null ||
    (typeof value === "number" && !Number.isSafeInteger(value))
  )
    return null
  return /^-?\d+$/.test(String(value)) ? BigInt(value) : null
}

export function paymentGroup(row: LedgerTransaction) {
  return `${row.currency}:${row.account_type === "credit_card" ? "card" : "bank"}`
}

export type ProfileScope = "owned_accounts" | "counterparty_payments"
export interface ProfileAccount {
  id: string
  label: string
  currency: string | null
  relationships: AccountParties["accounts"][number]["relationships"]
}
export interface PaymentProfile {
  id: string
  name: string
  kind: "account" | "name" | "owner"
  unidentified: boolean
  rows: LedgerTransaction[]
  counterpartyRows: LedgerTransaction[]
  accounts: string[]
  accountDetails: ProfileAccount[]
  nestedUnderOwner: boolean
  sources: string[]
  first: string | null
  last: string | null
}

/** A reviewed holder relationship applies only within its recorded dates. */
export function ownsPayment(row: LedgerTransaction, partyId: string) {
  const links = (row.account_relationships ?? []).filter(
    (link) => link.role === "holder" && link.party.id === partyId
  )
  if (!links.length)
    return (
      !row.account_relationships?.length &&
      !!row.account_holder_parties?.some((party) => party.id === partyId)
    )
  const day = paymentDay(row)
  return links.some(
    (link) =>
      (!link.effective_from && !link.effective_to) ||
      (!!day &&
        (!link.effective_from || day >= link.effective_from) &&
        (!link.effective_to || day <= link.effective_to))
  )
}

export function paymentProfiles(
  rows: LedgerTransaction[],
  directory: AccountParties["accounts"] = []
): PaymentProfile[] {
  type Group = {
    name: string
    kind: PaymentProfile["kind"]
    rows: Map<string, LedgerTransaction>
    counterpartyRows: Map<string, LedgerTransaction>
    accounts: Map<string, ProfileAccount>
    nestedUnderOwner: boolean
  }
  const groups = new Map<string, Group>()
  const ensure = (id: string, name: string, kind: PaymentProfile["kind"]) => {
    let group = groups.get(id)
    if (!group) {
      group = {
        name,
        kind,
        rows: new Map(),
        counterpartyRows: new Map(),
        accounts: new Map(),
        nestedUnderOwner: false,
      }
      groups.set(id, group)
    }
    return group
  }
  for (const account of directory) {
    const id = account.canonical_id || account.id
    const detail = {
      id,
      label:
        [
          account.institution,
          account.identifier_as_printed,
          account.holder_as_recorded,
        ]
          .filter(Boolean)
          .join(" · ") || "Account details missing",
      currency: account.currency,
      relationships: account.relationships,
    }
    const accountGroup = ensure(`account:${id}`, detail.label, "account")
    // Prefer the canonical account label while retaining alias relationships.
    if (account.id === id) accountGroup.name = detail.label
    const existing = accountGroup.accounts.get(id)
    accountGroup.accounts.set(id, {
      ...detail,
      relationships: [
        ...(existing?.relationships || []),
        ...detail.relationships,
      ].filter(
        (link, index, all) =>
          all.findIndex((other) => other.id === link.id) === index
      ),
    })
    for (const party of account.holder_parties) {
      const owner = ensure(`owner:${party.id}`, party.name, "owner")
      const prior = owner.accounts.get(id)
      owner.accounts.set(id, {
        ...detail,
        relationships: [
          ...(prior?.relationships || []),
          ...detail.relationships,
        ].filter(
          (link, index, all) =>
            all.findIndex((other) => other.id === link.id) === index
        ),
      })
      accountGroup.nestedUnderOwner = true
    }
  }
  for (const row of rows) {
    const id = row.canonical_account_id || row.account_id
    const own = ensure(
      `account:${id}`,
      row.canonical_account_label ||
        row.account_label ||
        "Account name not recorded",
      "account"
    )
    own.rows.set(row.key, row)
    if (!own.accounts.has(id))
      own.accounts.set(id, {
        id,
        label: own.name,
        currency: row.currency,
        relationships: row.account_relationships || [],
      })
    const name =
      (row.direction === "credit" ? row.from_name : row.to_name) ??
      row.counterparty_raw
    const link = row.counterparty_link
    if (link) {
      const other = ensure(
        `${link.kind === "party" ? "owner" : "account"}:${link.id}`,
        link.label || name || "Name not recorded",
        link.kind === "party" ? "owner" : "account"
      )
      other.counterpartyRows.set(row.key, row)
    } else {
      ensure(
        `name:${name ?? ""}`,
        name?.trim() ? name : "Name not recorded",
        "name"
      ).rows.set(row.key, row)
    }
    for (const party of row.account_holder_parties ?? []) {
      const owner = ensure(`owner:${party.id}`, party.name, "owner")
      own.nestedUnderOwner = true
      if (!owner.accounts.has(id)) owner.accounts.set(id, own.accounts.get(id)!)
      if (ownsPayment(row, party.id)) owner.rows.set(row.key, row)
    }
  }
  return [...groups].map(([id, group]) => {
    const rows = [...group.rows.values()]
    const dates = rows
      .flatMap((row) => (paymentDay(row) ? [paymentDay(row)!] : []))
      .sort()
    return {
      id,
      name: group.name,
      kind: group.kind,
      nestedUnderOwner: group.nestedUnderOwner,
      rows,
      counterpartyRows: [...group.counterpartyRows.values()],
      unidentified: group.kind === "name" && !id.slice(5).trim(),
      accounts:
        group.kind === "name"
          ? [
              ...new Set(
                rows.map((row) => row.canonical_account_id || row.account_id)
              ),
            ]
          : [...group.accounts.keys()],
      accountDetails: [...group.accounts.values()],
      sources: [...new Set(rows.map((row) => row.source_document_id))],
      first: dates[0] ?? null,
      last: dates.at(-1) ?? null,
    }
  })
}

export interface PaymentComparison {
  incoming: LedgerTransaction
  outgoing: LedgerTransaction
  days: number
  difference: bigint
}

/** Adjacent dated entries only. This is a reproducible comparison, not a transfer match. */
export function nearbyPayments(
  rows: LedgerTransaction[],
  maximumDays = 7
): PaymentComparison[] {
  const accounts = new Map<string, LedgerTransaction[]>()
  for (const row of rows) {
    if (row.account_type === "credit_card" || !paymentDay(row)) continue
    const key = `${row.canonical_account_id || row.account_id}:${row.currency}`
    const group = accounts.get(key) ?? []
    group.push(row)
    accounts.set(key, group)
  }
  const result: PaymentComparison[] = []
  for (const group of accounts.values()) {
    const ordered = [...group].sort(
      (a, b) =>
        paymentDay(a)!.localeCompare(paymentDay(b)!) ||
        a.row_index - b.row_index ||
        a.key.localeCompare(b.key)
    )
    for (let index = 1; index < ordered.length; index++) {
      const incoming = ordered[index - 1],
        outgoing = ordered[index]
      if (incoming.direction !== "credit" || outgoing.direction !== "debit")
        continue
      const days =
        (Date.parse(paymentDay(outgoing)!) -
          Date.parse(paymentDay(incoming)!)) /
        86400000
      const credit = minorAmount(incoming.amount_minor),
        debit = minorAmount(outgoing.amount_minor)
      if (
        days <= maximumDays &&
        credit !== null &&
        debit !== null &&
        credit >= 0n &&
        debit >= 0n
      )
        result.push({ incoming, outgoing, days, difference: credit - debit })
    }
  }
  return result.sort((a, b) =>
    paymentDay(a.incoming)!.localeCompare(paymentDay(b.incoming)!)
  )
}

export interface PaymentPeriod {
  date: string
  end: string
  rows: LedgerTransaction[]
  credit: bigint
  debit: bigint
  unreadable: number
}

/** Monthly charts use observed months; daily comparisons retain their chosen window. */
export function paymentPeriods(
  rows: LedgerTransaction[],
  granularity: "month" | "day",
  start?: string,
  end?: string
): PaymentPeriod[] {
  const dated = rows.flatMap((row) =>
    paymentDay(row) ? [{ row, day: paymentDay(row)! }] : []
  )
  const dates = dated.map((item) => item.day).sort()
  const from = start || dates[0],
    to = end || dates.at(-1)
  if (
    !from ||
    !to ||
    from > to ||
    !/^\d{4}-\d{2}-\d{2}$/.test(from) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(to)
  )
    return []
  const grouped = new Map<string, LedgerTransaction[]>()
  for (const { row, day } of dated) {
    if (day < from || day > to) continue
    const key = granularity === "month" ? `${day.slice(0, 7)}-01` : day
    const bucket = grouped.get(key) ?? []
    bucket.push(row)
    grouped.set(key, bucket)
  }
  const cursor = new Date(
    `${granularity === "month" ? `${from.slice(0, 7)}-01` : from}T00:00:00Z`
  )
  const result: PaymentPeriod[] = []
  // Covers the complete requested range. Presentation windows are applied by the caller.
  while (
    Number.isFinite(cursor.getTime()) &&
    cursor.toISOString().slice(0, 10) <= to
  ) {
    const date = cursor.toISOString().slice(0, 10)
    const next = new Date(cursor)
    if (granularity === "month") next.setUTCMonth(next.getUTCMonth() + 1)
    else next.setUTCDate(next.getUTCDate() + 1)
    const period: PaymentPeriod = {
      date,
      end: new Date(next.getTime() - 86400000).toISOString().slice(0, 10),
      rows: grouped.get(date) ?? [],
      credit: 0n,
      debit: 0n,
      unreadable: 0,
    }
    for (const row of period.rows) {
      const amount = minorAmount(row.amount_minor)
      if (
        amount === null ||
        amount < 0n ||
        !["credit", "debit"].includes(row.direction)
      )
        period.unreadable++
      else period[row.direction as "credit" | "debit"] += amount
    }
    if (granularity !== "month" || period.rows.length) result.push(period)
    cursor.setTime(next.getTime())
  }
  return result
}

/** Chart coordinates only. All displayed amounts and saved values remain exact integers. */
export function chartRatio(value: bigint, maximum: bigint) {
  return maximum > 0n ? Number((value * 10000n) / maximum) / 10000 : 0
}
