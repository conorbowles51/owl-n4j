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
export const patternReview = z
  .object({
    schema: z.literal("loupe.financial.pattern_review/1"),
    case_id: z.string(),
    account_id: z.string().nullable(),
    start_date: z.string().nullable(),
    end_date: z.string().nullable(),
    population: z.enum(["working", "verified"]),
    cross_account: z.boolean().default(false),
    window_days: z.number().int().min(0).max(30),
    threshold_minor: z
      .string()
      .regex(/^[1-9][0-9]*$/)
      .nullable()
      .default(null),
    threshold_currency: z
      .string()
      .regex(/^[A-Z]{3}$/)
      .nullable()
      .default(null),
    snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    reviewed_rows: z.number().int().nonnegative(),
    date_unavailable_ids: z.array(z.string()),
    limitation: z.string(),
    hypotheses: z
      .array(
        z.object({
          id: z.string(),
          kind: z.enum([
            "repeated_equal_amount",
            "equal_amount_in_and_out",
            "split_payment_threshold",
            "possible_transfer_chain",
            "possible_return_flow",
          ]),
          transaction_ids: z.array(z.string()).min(2).max(50),
          gap_days: z.number().int().nonnegative(),
          account_id: z.string(),
          account_label: z.string(),
          currency: z.string(),
          amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
          sources: z.array(source).min(2).max(50),
          transfer_pairs: z
            .array(
              z
                .object({ debit_id: z.string(), credit_id: z.string() })
                .passthrough()
            )
            .min(2)
            .max(3)
            .optional(),
          explanation: z.string(),
          limitation: z.string(),
        })
      )
      .max(200),
  })
  .superRefine((data, ctx) => {
    for (const h of data.hypotheses) {
      if (!h.kind.startsWith("possible_")) continue
      const ids =
        h.transfer_pairs?.flatMap((p) => [p.debit_id, p.credit_id]) ?? []
      let valid =
        data.cross_account &&
        ids.length === h.transaction_ids.length &&
        ids.every(
          (id, i) => id === h.transaction_ids[i] && h.sources[i]?.row.key === id
        ) &&
        new Set(ids).size === ids.length
      const rows = h.sources.map((s) => s.row)
      for (let i = 0; i < rows.length; i += 2) {
        const d = rows[i],
          c = rows[i + 1]
        valid =
          valid &&
          !!c &&
          d.direction === "debit" &&
          c.direction === "credit" &&
          d.account_id !== c.account_id &&
          d.amount_minor === h.amount_minor &&
          c.amount_minor === h.amount_minor &&
          d.currency === h.currency &&
          c.currency === h.currency &&
          (i === 0 || rows[i - 1].account_id === d.account_id)
      }
      if (!valid)
        ctx.addIssue({
          code: "custom",
          message: "Candidate path does not match its supporting readings.",
        })
    }
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
    !scope.hypotheses.some((p) => JSON.stringify(p) === JSON.stringify(h)) ||
    h.sources.length !== h.transaction_ids.length ||
    new Set(h.transaction_ids).size !== h.transaction_ids.length ||
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
      `Cross-account chain screen: ${scope.cross_account ? "selected" : "not selected"}. Candidate pairings: ${JSON.stringify(h.transfer_pairs ?? [])}.`,
      `Optional screening threshold: ${scope.threshold_minor ?? "not selected"} minor units ${scope.threshold_currency ?? ""}. This is an investigator-selected criterion.`,
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
        cross_account: scope.cross_account,
        transfer_pairs: h.transfer_pairs,
        threshold_minor: scope.threshold_minor,
        threshold_currency: scope.threshold_currency,
        sources,
      },
    })),
  }
}
