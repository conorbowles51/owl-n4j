import { z } from "zod"
const minor = z.string().regex(/^-?(0|[1-9][0-9]*)$/)
export const statementDeltaHints = z.discriminatedUnion("available", [
  z.object({ available: z.literal(false), reason: z.string() }),
  z.object({
    available: z.literal(true),
    difference_minor: minor,
    rows_checked: z.number().int().nonnegative(),
    limitation: z.string(),
    candidates: z
      .array(
        z.object({
          transaction_id: z.string(),
          ref_id: z.string(),
          amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
          direction: z.enum(["credit", "debit"]),
          kind: z.enum(["direction_change", "extra_entry", "missing_entry"]),
          explanation: z.string(),
        })
      )
      .max(100),
    signatures: z.array(
      z.object({
        kind: z.enum([
          "transposition",
          "opening_omitted",
          "opening_sign_flipped",
        ]),
        explanation: z.string(),
      })
    ),
  }),
])
export type StatementDeltaHints = z.infer<typeof statementDeltaHints>
