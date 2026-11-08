import type { Transaction } from "../api"

export type SubSuggestion = {
  tx: Transaction
  level: "strong" | "moderate" | "weak" | "faint"
  reasons: string
}

const cents = (n: number) => Math.round(n * 100)
const day = (d?: string | null) => (d ? Date.parse(d.slice(0, 10)) : NaN)
const norm = (s?: string | null) => (s || "").trim().toLowerCase()

/**
 * Candidate parts of a payment, strongest first, by a stated rule (never a model): the amount fits what is left of
 * the parent (equals it 3, fits within it 2), the date is close (same day 3, within 3 days 2, within 31 days 1) and
 * a name is shared with the parent (same sender or recipient). Strong: a fitting amount within 3 days with a shared
 * name. Moderate: a fitting amount within 3 days or with a shared name. Weak: a fitting amount, a shared name or a
 * close date. Faint: anything else. Every candidate is kept; none is dropped for a low strength.
 */
export function rankSubTransactionCandidates(
  parent: Transaction,
  remaining: number | null,
  candidates: Transaction[]
): SubSuggestion[] {
  const ranked = candidates.map((tx) => {
    const reasons: string[] = []
    let amount = 0
    if (tx.amount === null || parent.amount === null) reasons.push("no amount to compare")
    else if (tx.currency !== parent.currency) reasons.push("another currency")
    else if (remaining !== null && cents(tx.amount) === cents(remaining)) {
      amount = 3
      reasons.push("equals the amount still unassigned")
    } else if (remaining !== null && cents(tx.amount) < cents(remaining)) {
      amount = 2
      reasons.push("fits within the amount still unassigned")
    } else if (remaining !== null) reasons.push("more than the amount still unassigned")
    const gap = Math.round(Math.abs(day(tx.date) - day(parent.date)) / 86_400_000)
    const date = Number.isNaN(gap) ? 0 : gap === 0 ? 3 : gap <= 3 ? 2 : gap <= 31 ? 1 : 0
    reasons.push(
      Number.isNaN(gap) ? "no date to compare" : gap === 0 ? "same day" : `${gap} day${gap === 1 ? "" : "s"} apart`
    )
    const shared = [
      norm(tx.from_entity?.name) && norm(tx.from_entity?.name) === norm(parent.from_entity?.name)
        ? "same sender"
        : "",
      norm(tx.to_entity?.name) && norm(tx.to_entity?.name) === norm(parent.to_entity?.name)
        ? "same recipient"
        : "",
    ].filter(Boolean)
    reasons.push(...shared)
    const names = shared.length
    const level: SubSuggestion["level"] =
      amount >= 2 && date >= 2 && names >= 1
        ? "strong"
        : amount >= 2 && (date >= 2 || names >= 1)
          ? "moderate"
          : amount >= 2 || names >= 1 || date >= 2
            ? "weak"
            : "faint"
    return { tx, level, reasons: reasons.join("; "), score: [amount, date, names, gap] as const }
  })
  const order = { strong: 0, moderate: 1, weak: 2, faint: 3 }
  ranked.sort(
    (a, b) =>
      order[a.level] - order[b.level] ||
      b.score[0] - a.score[0] ||
      b.score[1] + b.score[2] - (a.score[1] + a.score[2]) ||
      (Number.isNaN(a.score[3]) ? 1e9 : a.score[3]) - (Number.isNaN(b.score[3]) ? 1e9 : b.score[3]) ||
      a.tx.key.localeCompare(b.tx.key)
  )
  return ranked.map(({ tx, level, reasons }) => ({ tx, level, reasons }))
}
