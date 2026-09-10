import { expect, it } from "vitest"
import { patternReview, patternTheory } from "./pattern-review"
const source = (key: string) => ({
  row: {
    key,
    source_document_id: "source",
    account_id: "account",
    account_label: "Account",
    chronology_date: "2026-01-01",
    chronology_basis: "transaction_date",
    ordering_date: "2026-01-01",
    direction: "credit",
    amount_minor: "100",
    currency: "GBP",
    proof_class: "p3",
    description: "Original",
  },
  source: {
    id: "source",
    evidence_file_id: "00000000-0000-4000-8000-000000000001",
    sha256_at_ingestion: "a".repeat(64),
  },
  provenance: { locator: "original" },
})
export const review = patternReview.parse({
  schema: "loupe.financial.pattern_review/1",
  case_id: "case",
  account_id: null,
  start_date: null,
  end_date: null,
  population: "working",
  window_days: 3,
  snapshot_sha256: "b".repeat(64),
  reviewed_rows: 2,
  date_unavailable_ids: [],
  limitation: "Screen only",
  hypotheses: [
    {
      id: "pattern",
      kind: "repeated_equal_amount",
      transaction_ids: ["one", "two"],
      gap_days: 0,
      account_id: "account",
      account_label: "Account",
      currency: "GBP",
      amount_minor: "100",
      sources: [source("one"), source("two")],
      explanation: "Equal incoming amounts",
      limitation: "Not a finding",
    },
  ],
})
it("creates a proposed theory with grouped original evidence and no proof promotion", () => {
  const value = patternTheory(
    review,
    review.hypotheses[0],
    "Review equal payments",
    "Could be ordinary repeated payments; inspect the sources."
  )
  expect(value.entry_type).toBe("theory")
  expect(value.lifecycle_state).toBe("proposed")
  expect(value.links).toHaveLength(1)
  expect(value.links?.[0].relationship).toBe("context")
  expect(value.links?.[0].source_anchor).toEqual({
    financial_transaction_ids: ["one", "two"],
  })
  expect(JSON.stringify(value.links?.[0].metadata)).toContain(
    '"proof_class":"p3"'
  )
  expect(value.body).toContain(review.snapshot_sha256)
})
it("refuses missing reasoning, missing source links and mismatched support", () => {
  expect(() =>
    patternTheory(review, review.hypotheses[0], "Title", " ")
  ).toThrow("Explain")
  const h = structuredClone(review.hypotheses[0])
  h.sources[0].source.evidence_file_id = null
  expect(() => patternTheory(review, h, "Title", "Reason")).toThrow(
    "unavailable"
  )
  h.sources[0].source.evidence_file_id = "00000000-0000-4000-8000-000000000001"
  h.sources[0].row.key = "wrong"
  expect(() => patternTheory(review, h, "Title", "Reason")).toThrow(
    "inconsistent"
  )
})
