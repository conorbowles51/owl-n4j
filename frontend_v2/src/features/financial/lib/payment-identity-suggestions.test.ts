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
