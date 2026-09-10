import type { z } from "zod"
import type { counterpartyParties } from "./counterparty-parties"

type Reading = z.infer<typeof counterpartyParties>["readings"][number]
export interface PaymentIdentitySuggestion {
  key: string
  labels: string[]
  readings: Reading[]
  alternatives: { party: NonNullable<Reading["party"]>; anchors: Reading[] }[]
}

// Whitespace and case only. No fuzzy identity or punctuation/diacritic removal.
const keyOf = (label: string | null) =>
  label?.trim().replace(/\s+/g, " ").toLowerCase() ?? ""
export function paymentIdentitySuggestions(
  readings: Reading[]
): PaymentIdentitySuggestion[] {
  const groups = new Map<string, Reading[]>()
  for (const reading of readings) {
    const key = keyOf(reading.counterparty_raw)
    if (!key) continue
    const group = groups.get(key) ?? []
    group.push(reading)
    groups.set(key, group)
  }
  const results: PaymentIdentitySuggestion[] = []
  for (const [key, rows] of groups) {
    // An explicit removal is a durable decision, never a new import proposal.
    const unlinked = rows.filter(
      (r) => r.party === null && r.decision_transaction_id === null
    )
    const anchors = rows.filter(
      (r) => r.party !== null && r.decision_transaction_id !== null
    )
    if (!unlinked.length || !anchors.length) continue
    const parties = new Map<
      string,
      { party: NonNullable<Reading["party"]>; anchors: Reading[] }
    >()
    for (const anchor of anchors) {
      const party = anchor.party!
      const entry = parties.get(party.id) ?? { party, anchors: [] }
      entry.anchors.push(anchor)
      parties.set(party.id, entry)
    }
    results.push({
      key,
      labels: [...new Set(rows.map((r) => r.counterparty_raw!))].sort(),
      readings: unlinked,
      alternatives: [...parties.values()].sort((a, b) =>
        a.party.id.localeCompare(b.party.id)
      ),
    })
  }
  return results.sort((a, b) => a.key.localeCompare(b.key))
}
