import { expect, it } from "vitest"
import { paymentIdentitySuggestions } from "./payment-identity-suggestions"
const base = {
  transaction_id: "a",
  ref_id: "TX-A",
  account_id: "account",
  currency: "GBP",
  counterparty_raw: "ACME Ltd",
  description: null,
  amount_minor: "100",
  direction: "credit" as const,
  party: null,
  decision_transaction_id: null,
}
const anchor = {
  ...base,
  transaction_id: "anchor",
  party: { id: "party-a", name: "Reviewed ACME" },
  decision_transaction_id: "anchor",
}
it("proposes whitespace/case variants with original names and exact supporting readings", () => {
  const candidate = { ...base, counterparty_raw: " acme  LTD " }
  const result = paymentIdentitySuggestions([anchor, candidate])
  expect(result).toHaveLength(1)
  expect(result[0].readings).toEqual([candidate])
  expect(result[0].alternatives).toEqual([
    { party: anchor.party, anchors: [anchor] },
  ])
  expect(result[0].labels).toEqual([" acme  LTD ", "ACME Ltd"])
  expect(candidate.party).toBeNull()
})
it("preserves conflicting identities without choosing a winner", () => {
  const other = {
    ...anchor,
    transaction_id: "other",
    party: { id: "party-b", name: "Different ACME" },
  }
  const result = paymentIdentitySuggestions([anchor, other, base])
  expect(result[0].alternatives).toHaveLength(2)
  expect(result[0].readings).toEqual([base])
})
it("never reoffers explicit cleared links, blank labels or fuzzy matches", () => {
  const result = paymentIdentitySuggestions([
    anchor,
    { ...base, decision_transaction_id: "previous-decision" },
    { ...base, transaction_id: "blank", counterparty_raw: " " },
    { ...base, transaction_id: "punctuation", counterparty_raw: "ACME, Ltd" },
    { ...base, transaction_id: "accent", counterparty_raw: "ÁCME Ltd" },
  ])
  expect(result).toEqual([])
})
it("requires a reviewed supporting payment and retains more than100 candidates", () => {
  expect(paymentIdentitySuggestions([base])).toEqual([])
  const rows = Array.from({ length: 101 }, (_, i) => ({
    ...base,
    transaction_id: String(i),
  }))
  expect(
    paymentIdentitySuggestions([anchor, ...rows])[0].readings
  ).toHaveLength(101)
})

it("offers optional formatting and spelling alternatives while preserving their raw sources", () => {
  const reviewed = { ...anchor, counterparty_raw: "José OBrien Ltd" }
  const candidate = { ...base, counterparty_raw: "Ltd Jose OBrien" }
  const typo = {
    ...base,
    transaction_id: "typo",
    counterparty_raw: "Jose OBrlen Ltd",
  }
  expect(paymentIdentitySuggestions([reviewed, candidate, typo])).toEqual([])
  const result = paymentIdentitySuggestions([reviewed, candidate, typo], true)
  expect(result).toHaveLength(2)
  expect(result.flatMap((g) => g.readings)).toEqual(
    expect.arrayContaining([candidate, typo])
  )
  expect(
    result.flatMap((g) => g.alternatives.flatMap((a) => a.reasons ?? []))
  ).toEqual(
    expect.arrayContaining([
      "Similar after punctuation, accents or word-order normalization",
      "One character differs after formatting normalization",
    ])
  )
  expect(result.every((g) => g.alternatives[0].anchors[0] === reviewed)).toBe(
    true
  )
  expect(candidate.party).toBeNull()
})
it("retains ambiguity and cleared decisions in variant mode", () => {
  const other = {
    ...anchor,
    transaction_id: "other",
    counterparty_raw: "Acme, Ltd",
    party: { id: "other-party", name: "Separate business" },
  }
  const candidate = { ...base, counterparty_raw: "ACME. LTD" }
  const result = paymentIdentitySuggestions(
    [
      anchor,
      other,
      candidate,
      {
        ...candidate,
        transaction_id: "cleared",
        decision_transaction_id: "decision",
      },
    ],
    true
  )
  expect(result).toHaveLength(1)
  expect(result[0].readings).toEqual([candidate])
  expect(result[0].alternatives.map((a) => a.party.id)).toEqual([
    "other-party",
    "party-a",
  ])
})
it("does not fuzz short names, different numeric identifiers or two unrelated character changes", () => {
  for (const [known, unknown] of [
    ["Ann", "Ana"],
    ["Company 123", "Company 124"],
    ["Longname Trading", "Longnome Troding"],
  ]) {
    expect(
      paymentIdentitySuggestions(
        [
          { ...anchor, counterparty_raw: known },
          { ...base, counterparty_raw: unknown },
        ],
        true
      )
    ).toEqual([])
  }
})
