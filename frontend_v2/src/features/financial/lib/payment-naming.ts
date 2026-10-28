/**
 * Naming the other side of a payment from its statement line, one payment after another.
 *
 * Pure functions only: which payments still need a name, where the payment's line sits on its page and how much
 * of the page around it to show, the names already used in the case, and which other payments look like the one
 * just named. Nothing here saves; `PaymentNamingPanel` does, through the person label path.
 */
import type { LedgerTransaction } from "../api"
import { readLocator } from "./locator"

export type NameField = "from_name" | "to_name"

/** The side of the payment that is not the account holder: who paid in, or who was paid. */
export function otherSide(row: Pick<LedgerTransaction, "direction">): NameField {
  return row.direction === "credit" ? "from_name" : "to_name"
}

/**
 * True while nobody is named for the other side: no printed or suggested name and no person's label. A person who
 * saved an empty name decided there is none, so the payment is not asked about again.
 */
export function needsName(row: LedgerTransaction) {
  const field = otherSide(row)
  if (row.counterparty_link) return false
  if (row.label_sources?.[field]?.source === "investigator") return false
  return !(row[field] ?? "").trim() && !(row.counterparty_raw ?? "").trim()
}

/** Why the statement gives no name, in the words the ledger shows, or null when nothing is known. */
export function missingNameReason(row: LedgerTransaction) {
  const source = row.label_sources?.[otherSide(row)]
  return source?.reason ? { reason: source.reason, explanation: source.explanation } : null
}

/** A payment's printed line as fractions of its page (0 = top/left edge, 1 = bottom/right edge). */
export interface LineBand {
  page: number
  top: number
  bottom: number
  left: number
  right: number
}

export function lineBand(locator: unknown): LineBand | null {
  const reading = readLocator(locator)
  if (!reading.ok || reading.locator.kind !== "page_rectangle") return null
  const r = reading.locator.rectangle
  return {
    page: r.page,
    top: r.y0 / r.pageHeight,
    bottom: r.y1 / r.pageHeight,
    left: r.x0 / r.pageWidth,
    right: r.x1 / r.pageWidth,
  }
}

/** The stored page of a payment, for either locator kind that knows one. */
export function locatorPage(locator: unknown): number | null {
  const reading = readLocator(locator)
  if (!reading.ok) return null
  const l = reading.locator
  return l.kind === "page_rectangle" || l.kind === "page_only" ? l.page : null
}

/**
 * The part of the page to show around the line: a few printed lines above and more below, because a payee is often
 * printed on the line after the amount. Line height is the band's own height (at least 0.8% of the page).
 */
export function cropWindow(band: Pick<LineBand, "top" | "bottom">, linesAbove = 4, linesBelow = 6) {
  const line = Math.max(band.bottom - band.top, 0.008)
  const top = Math.max(0, band.top - line * linesAbove)
  const bottom = Math.min(1, band.bottom + line * linesBelow)
  return { top, bottom, cutAtBottom: band.bottom + line * linesBelow > 1 }
}

/** Whether the next page's top is worth showing: the payment is its page's last, or its window runs off the page. */
export function showNextPageTop(band: LineBand | null, lastOnPage: boolean | null | undefined, pageCount: number | null | undefined) {
  if (!band || !pageCount || band.page >= pageCount) return false
  return lastOnPage === true || cropWindow(band).cutAtBottom || band.bottom > 0.85
}

/**
 * Names already used in the case for either side, most used first: what people saved, what the statements print or
 * the case suggests, and the account holders. Offered while typing so one party is spelled one way.
 */
export function caseNames(rows: LedgerTransaction[], limit = 400) {
  const counts = new Map<string, { name: string; count: number }>()
  const add = (value: string | null | undefined, weight = 1) => {
    const name = (value ?? "").trim().replace(/\s+/g, " ")
    if (name.length < 2) return
    const key = name.toLocaleUpperCase()
    const entry = counts.get(key) ?? { name, count: 0 }
    entry.count += weight
    counts.set(key, entry)
  }
  for (const row of rows) {
    for (const field of ["from_name", "to_name"] as const) {
      const source = row.label_sources?.[field]?.source
      if (source === "missing") continue
      add(row[field], source === "investigator" ? 3 : 1)
    }
    add(row.account_holder)
    for (const holder of row.account_holder_parties ?? []) add(holder.name)
  }
  return [...counts.values()]
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    .slice(0, limit)
    .map((entry) => entry.name)
}

/** The printed text with every number replaced, so payments that differ only in references and amounts match. */
export function descriptionPattern(description: string | null | undefined) {
  const text = (description ?? "").toLocaleUpperCase().replace(/\s+/g, " ").trim()
  if (!text) return ""
  return text.replace(/[0-9]+/g, "#").replace(/#(?:[ .,/-]?#)+/g, "#")
}

/** The other side's account as printed: the transfer's account field, else a 10-18 digit number on the line. */
export function counterpartyAccount(row: LedgerTransaction) {
  const details = row.transfer_details
  const role = row.direction === "credit" ? "sender" : "recipient"
  const printed = details?.[role]?.account?.text?.replace(/\D/g, "")
  if (printed && printed.length >= 6) return printed
  const numbers = (row.description ?? "").match(/(?<![0-9])[0-9]{10,18}(?![0-9])/g) ?? []
  return numbers.length === 1 ? numbers[0] : ""
}

/** The leading part of a SPEI tracking key (clave de rastreo): the issuing system and date, not the serial. */
export function trackingPrefix(row: LedgerTransaction) {
  const match = (row.description ?? "").match(/(?:CLAVE DE RASTREO|CVE\.? ?RASTREO|RASTREO)[:\s]*([A-Z0-9]{8,})/i)
  return match ? match[1].toUpperCase().slice(0, 10) : ""
}

export interface SimilarGroup {
  key: "pattern" | "account" | "tracking"
  label: string
  /** Groups a person usually wants are ticked; a weaker likeness starts unticked. */
  preselected: boolean
  rows: LedgerTransaction[]
}

/**
 * Other unnamed payments like `named`, in three separate groups, each payment in the first group it fits:
 * the same printed text apart from numbers (same account, same direction); the same account paying or paid by the
 * same other-side account; the same tracking-key prefix. Shown with checkboxes; never applied without a click.
 */
export function similarPayments(named: LedgerTransaction, rows: LedgerTransaction[]): SimilarGroup[] {
  const candidates = rows.filter(
    (row) => row.key !== named.key && row.case_id === named.case_id && row.direction === named.direction && needsName(row)
  )
  const taken = new Set<string>()
  const group = (key: SimilarGroup["key"], label: string, preselected: boolean, test: (row: LedgerTransaction) => boolean) => {
    const matched = candidates.filter((row) => !taken.has(row.key) && test(row))
    matched.forEach((row) => taken.add(row.key))
    return { key, label, preselected, rows: matched }
  }
  const pattern = descriptionPattern(named.description)
  const account = counterpartyAccount(named)
  const tracking = trackingPrefix(named)
  return [
    group("account", `Same account, same other-side account (${account})`, true, (row) =>
      !!account && row.account_id === named.account_id && counterpartyAccount(row) === account
    ),
    group("pattern", "Same printed text apart from numbers, same account", true, (row) =>
      !!pattern && /[A-Z]{3}/.test(pattern) && row.account_id === named.account_id && descriptionPattern(row.description) === pattern
    ),
    group("tracking", `Same tracking key prefix (${tracking})`, false, (row) => !!tracking && trackingPrefix(row) === tracking),
  ].filter((entry) => entry.rows.length > 0)
}

/** The row as the table shows it once a person's name is saved on its other side. */
export function withPersonName(row: LedgerTransaction, name: string, explanation: string): LedgerTransaction {
  const field = otherSide(row)
  return {
    ...row,
    [field]: name,
    label_version: (row.label_version ?? 0) + 1,
    label_sources: { ...row.label_sources, [field]: { source: "investigator", explanation } },
  }
}
