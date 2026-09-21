import type { LedgerTransaction } from "../api"

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

export interface PaymentProfile {
  id: string
  name: string
  kind: "account" | "name"
  unidentified: boolean
  rows: LedgerTransaction[]
  accounts: string[]
  sources: string[]
  first: string | null
  last: string | null
}

export function paymentProfiles(rows: LedgerTransaction[]): PaymentProfile[] {
  const groups = new Map<
    string,
    { name: string; kind: "account" | "name"; rows: LedgerTransaction[] }
  >()
  for (const row of rows) {
    const counterparty =
      (row.direction === "credit" ? row.from_name : row.to_name) ??
      row.counterparty_raw
    for (const [id, name, kind] of [
      [
        `account:${row.account_id}`,
        row.account_label || "Account name not recorded",
        "account",
      ],
      [
        `name:${counterparty ?? ""}`,
        counterparty?.trim() ? counterparty : "Name not recorded",
        "name",
      ],
    ] as const) {
      const group = groups.get(id) ?? { name, kind, rows: [] }
      group.rows.push(row)
      groups.set(id, group)
    }
  }
  return [...groups].map(([id, group]) => {
    const dates = group.rows
      .flatMap((row) => (paymentDay(row) ? [paymentDay(row)!] : []))
      .sort()
    return {
      id,
      ...group,
      unidentified: group.kind === "name" && !id.slice(5).trim(),
      accounts: [...new Set(group.rows.map((row) => row.account_id))],
      sources: [...new Set(group.rows.map((row) => row.source_document_id))],
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
    const key = `${row.account_id}:${row.currency}`
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

/** Fill the calendar, but an empty bucket means no imported entries, not proven inactivity. */
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
    result.push(period)
    cursor.setTime(next.getTime())
  }
  return result
}

/** Chart coordinates only. All displayed amounts and saved values remain exact integers. */
export function chartRatio(value: bigint, maximum: bigint) {
  return maximum > 0n ? Number((value * 10000n) / maximum) / 10000 : 0
}
