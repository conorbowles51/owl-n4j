import { z } from "zod"
import { ledgerTimeline } from "./ledger-timeline"
import type { CaseworkCreateInput } from "@/features/workspace/casework-api"
const source = z.object({
  row: ledgerTimeline.shape.rows.element,
  source: z
    .object({
      id: z.string(),
      evidence_file_id: z.string().uuid().nullable(),
      sha256_at_ingestion: z.string(),
    })
    .passthrough(),
  provenance: z.unknown(),
})
export const patternReview = z.object({
  schema: z.literal("loupe.financial.pattern_review/1"),
  case_id: z.string(),
  account_id: z.string().nullable(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  population: z.enum(["working", "verified"]),
  window_days: z.number().int().min(0).max(30),
  snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  reviewed_rows: z.number().int().nonnegative(),
  date_unavailable_ids: z.array(z.string()),
  limitation: z.string(),
  hypotheses: z
    .array(
      z.object({
        id: z.string(),
        kind: z.enum(["repeated_equal_amount", "equal_amount_in_and_out"]),
        transaction_ids: z.array(z.string()).length(2),
        gap_days: z.number().int().nonnegative(),
        account_id: z.string(),
        account_label: z.string(),
        currency: z.string(),
        amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
        sources: z.array(source).length(2),
        explanation: z.string(),
        limitation: z.string(),
      })
    )
    .max(200),
})
export type PatternReview = z.infer<typeof patternReview>
export function patternTheory(
  scope: PatternReview,
  h: PatternReview["hypotheses"][number],
  title: string,
  reason: string
): CaseworkCreateInput {
  if (!title.trim() || !reason.trim())
    throw Error("Explain the hypothesis before saving it.")
  if (
    !scope.hypotheses.some((p) => p.id === h.id) ||
    h.sources.some(
      (s, i) => s.row.key !== h.transaction_ids[i] || !s.source.evidence_file_id
    )
  )
    throw Error("Supporting evidence links are unavailable or inconsistent.")
  const byFile = new Map<string, typeof h.sources>()
  for (const source of h.sources) {
    const file = source.source.evidence_file_id!
    byFile.set(file, [...(byFile.get(file) ?? []), source])
  }
  return {
    entry_type: "theory",
    lifecycle_state: "proposed",
    title: title.trim(),
    body: [
      reason.trim(),
      "Screening basis: " + h.explanation,
      h.limitation,
      `Population: ${scope.population}. Date window: ${scope.window_days} days. Supporting ledger readings: ${h.transaction_ids.join(", ")}.`,
      `Captured ledger: ${scope.snapshot_sha256}. This theory records the captured readings; later corrections must be reviewed separately.`,
    ].join("\n\n"),
    tags: ["financial", "screening-hypothesis", h.kind],
    links: [...byFile].map(([file, sources]) => ({
      target_type: "evidence",
      target_id: file,
      relationship: "context",
      source_anchor: {
        financial_transaction_ids: sources.map((s) => s.row.key),
      },
      metadata: {
        schema: "loupe.financial.pattern_support/1",
        pattern_id: h.id,
        snapshot_sha256: scope.snapshot_sha256,
        population: scope.population,
        window_days: scope.window_days,
        sources,
      },
    })),
  }
}
