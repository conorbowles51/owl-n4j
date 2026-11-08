import type { LedgerTransaction } from "../api"
import { correctionMoney } from "./correction-contract"

/** The statement values a person may correct from the payment card (the correction path's own fields). */
export type CardValues = {
  amount_minor: string
  direction: "credit" | "debit"
  date: string
  description: string
  bank_reference: string
}

/** The printed date the ledger orders by is the one a person corrects as "the date". */
export function dateField(row: Pick<LedgerTransaction, "ordering_date_source">) {
  const field = `${row.ordering_date_source}_date`
  return (["transaction_date", "posted_date", "value_date", "effective_date"] as const).find((name) => name === field) ??
    "transaction_date"
}

export function cardValues(row: LedgerTransaction): CardValues {
  return {
    amount_minor: String(row.amount_minor),
    direction: row.direction === "credit" ? "credit" : "debit",
    date: row[dateField(row)] ?? row.ordering_date ?? "",
    description: row.description ?? "",
    bank_reference: row.bank_reference ?? "",
  }
}

/** Only the printed fields that differ, keyed as the correction path names them; an emptied field is null. */
export function fieldChanges(row: LedgerTransaction, next: CardValues): Record<string, string | null> {
  const before = cardValues(row)
  const changes: Record<string, string | null> = {}
  if (next.date !== before.date) changes[dateField(row)] = next.date || null
  if (next.description !== before.description) changes.description = next.description || null
  if (next.bank_reference !== before.bank_reference) changes.bank_reference = next.bank_reference || null
  return changes
}

const side = (row: Pick<LedgerTransaction, "account_type">, direction: string) =>
  row.account_type === "credit_card"
    ? direction === "credit" ? "card credits" : "card charges"
    : direction === "credit" ? "money in" : "money out"

/**
 * What an amount, direction or date change does to the account, in words, before it is saved:
 * "This raises the account's money out by 825.62 USD (from 100.00 USD to 925.62 USD)."
 */
export function whatChanges(row: LedgerTransaction, next: CardValues): string[] {
  const before = cardValues(row)
  const lines: string[] = []
  const money = (minor: bigint) => correctionMoney(String(minor), row.currency)
  const was = BigInt(before.amount_minor)
  const now = /^\d+$/.test(next.amount_minor) ? BigInt(next.amount_minor) : null
  if (now !== null && next.direction !== before.direction)
    lines.push(
      `This moves the payment from the account's ${side(row, before.direction)} to its ${side(row, next.direction)}: ` +
        `${side(row, before.direction)} falls by ${money(was)} and ${side(row, next.direction)} rises by ${money(now)}.`
    )
  else if (now !== null && now !== was)
    lines.push(
      `This ${now > was ? "raises" : "lowers"} the account's ${side(row, next.direction)} by ${money(now > was ? now - was : was - now)} ` +
        `(from ${money(was)} to ${money(now)}).`
    )
  if (next.date !== before.date)
    lines.push(
      `This moves the payment from ${before.date || "no date"} to ${next.date || "no date"}: the statement period it ` +
        "counts in and the running balance order can change."
    )
  return lines
}

/** The statement's balances closed before the change and would not after it. */
export function stopsClosing(identity?: { current: { status: string }; proposed: { status: string } } | null) {
  return !!identity && identity.current.status === "balanced" && identity.proposed.status !== "balanced"
}

/** A corrected payment's statement reading and who corrected it (GET /ledger/{id}/source, "corrected_from"). */
export type CorrectedFrom = {
  statement_read: Partial<Record<keyof CardValues | "transaction_date" | "posted_date" | "value_date" | "effective_date" | "currency", string | null>>
  statement_ref_id: string
  corrections: { actor_name: string | null; at: string | null; reason: string | null; by_model: boolean }[]
}

/** "Statement read: 100.00 USD money out, 2024-03-01 · corrected by Alex Rivera, 2026-11-08". */
export function correctedLine(row: LedgerTransaction, history: CorrectedFrom): string | null {
  const read = history.statement_read
  const now = cardValues(row)
  const parts: string[] = []
  if (read.amount_minor && (read.amount_minor !== now.amount_minor || read.direction !== now.direction))
    parts.push(`${correctionMoney(read.amount_minor, read.currency || row.currency)} ${side(row, read.direction || "debit")}`)
  const readDate = read[dateField(row)]
  if (readDate !== undefined && (readDate ?? "") !== now.date) parts.push(readDate || "no date")
  if (read.description !== undefined && (read.description ?? "") !== now.description) parts.push(`"${read.description ?? ""}"`)
  if (read.bank_reference !== undefined && (read.bank_reference ?? "") !== now.bank_reference)
    parts.push(`reference ${read.bank_reference || "none"}`)
  const last = history.corrections.at(-1)
  const who = last ? `${last.actor_name || "someone not recorded"}${last.at ? `, ${last.at.slice(0, 10)}` : ""}` : ""
  if (!parts.length) return `Corrected by ${who}; the values now match the statement's reading.`
  return `Statement read: ${parts.join(", ")} · corrected by ${who}`
}
