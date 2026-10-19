import type { z } from "zod"
import type { counterpartyParties } from "./counterparty-parties"

type Reading = z.infer<typeof counterpartyParties>["readings"][number]
export interface PaymentIdentitySuggestion {
  key: string
  labels: string[]
  readings: Reading[]
  alternatives: {
    party: NonNullable<Reading["party"]>
    anchors: Reading[]
    reasons?: string[]
  }[]
}

// Whitespace and case only. No fuzzy identity or punctuation/diacritic removal.
const keyOf = (label: string | null) =>
  label?.trim().replace(/\s+/g, " ").toLowerCase() ?? ""
export function paymentIdentitySuggestions(
  readings: Reading[],
  includeVariants = false
): PaymentIdentitySuggestion[] {
  const groups = new Map<string, Reading[]>()
  for (const reading of readings) {
    const key = keyOf(reading.counterparty_raw)
    if (!key) continue
    const group = groups.get(key) ?? []
    group.push(reading)
    groups.set(key, group)
  }
  const anchorGroups = [...groups.values()]
    .map((rows) =>
      rows.filter((r) => r.party !== null && r.decision_transaction_id !== null)
    )
    .filter((rows) => rows.length)
  const normalizedIndex = new Map<string, Reading[]>()
  const deletionIndex = new Map<string, Set<string>>()
  if (includeVariants)
    for (const anchors of anchorGroups) {
      const normalized = variantKey(anchors[0].counterparty_raw!)
      if (!normalized) continue
      normalizedIndex.set(normalized, [
        ...(normalizedIndex.get(normalized) ?? []),
        ...anchors,
      ])
      if (normalized.length >= 8 && normalized.length <= 80)
        for (const key of deletionKeys(normalized)) {
          const values = deletionIndex.get(key) ?? new Set<string>()
          values.add(normalized)
          deletionIndex.set(key, values)
        }
    }
  const results: PaymentIdentitySuggestion[] = []
  for (const [key, rows] of groups) {
    // An explicit removal is a durable decision, never a new import proposal.
    const unlinked = rows.filter(
      (r) => r.party === null && r.decision_transaction_id === null
    )
    let anchors = rows.filter(
      (r) => r.party !== null && r.decision_transaction_id !== null
    )
    if (!unlinked.length) continue
    const reasons = new Map<string, string>()
    for (const anchor of anchors)
      reasons.set(
        anchor.transaction_id,
        "Same source name after case and spacing normalization"
      )
    if (includeVariants) {
      const normalized = variantKey(key)
      const candidates = new Set<string>(
        normalizedIndex.has(normalized) ? [normalized] : []
      )
      if (normalized.length >= 8 && normalized.length <= 80)
        for (const deletion of deletionKeys(normalized))
          for (const match of deletionIndex.get(deletion) ?? []) {
            if (
              sameNumbers(normalized, match) &&
              oneEditApart(normalized, match)
            )
              candidates.add(match)
          }
      for (const match of candidates)
        for (const anchor of normalizedIndex.get(match) ?? []) {
          if (reasons.has(anchor.transaction_id)) continue
          anchors = [...anchors, anchor]
          reasons.set(
            anchor.transaction_id,
            normalized === match
              ? "Similar after punctuation, accents or word-order normalization"
              : "One character differs after formatting normalization"
          )
        }
    }
    if (!anchors.length) continue
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
      labels: [
        ...new Set([...rows, ...anchors].map((r) => r.counterparty_raw!)),
      ].sort(),
      readings: unlinked,
      alternatives: [...parties.values()]
        .sort((a, b) => a.party.id.localeCompare(b.party.id))
        .map((alternative) =>
          includeVariants
            ? {
                ...alternative,
                reasons: [
                  ...new Set(
                    alternative.anchors.map(
                      (a) => reasons.get(a.transaction_id)!
                    )
                  ),
                ],
              }
            : alternative
        ),
    })
  }
  return results.sort((a, b) => a.key.localeCompare(b.key))
}

// Deliberately a review aid: normalization is not an identity assertion.
const variantKey = (label: string) =>
  label
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .match(/[\p{L}\p{N}]+/gu)
    ?.sort()
    .join(" ") ?? ""
const sameNumbers = (a: string, b: string) =>
  JSON.stringify(a.match(/\p{N}+/gu) ?? []) ===
  JSON.stringify(b.match(/\p{N}+/gu) ?? [])
function deletionKeys(value: string) {
  const chars = Array.from(value)
  return new Set([
    value,
    ...chars.map((_, i) => chars.filter((_, n) => n !== i).join("")),
  ])
}
function oneEditApart(a: string, b: string) {
  const aa = Array.from(a),
    bb = Array.from(b)
  if (Math.abs(aa.length - bb.length) > 1) return false
  let i = 0,
    j = 0,
    edits = 0
  while (i < aa.length && j < bb.length) {
    if (aa[i] === bb[j]) {
      i++
      j++
      continue
    }
    if (++edits > 1) return false
    if (aa.length >= bb.length) i++
    if (bb.length >= aa.length) j++
  }
  return edits + (i < aa.length ? 1 : 0) + (j < bb.length ? 1 : 0) <= 1
}
