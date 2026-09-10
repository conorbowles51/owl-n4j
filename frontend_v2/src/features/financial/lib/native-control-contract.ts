import { z } from "zod"

const check = z.object({
  scope: z.string(),
  kind: z.string(),
  result: z
    .object({
      status: z.enum([
        "balanced",
        "unbalanced",
        "unavailable",
        "not_attempted",
      ]),
    })
    .catchall(z.unknown()),
})
const calculation = z.object({
  format: z.enum(["camt053", "bai2", "mt940", "nacha"]),
  checks: z.array(check),
  mapped_rows: z.number().int().nonnegative(),
  unmapped_rows_retained: z.number().int().nonnegative(),
  basis: z.string(),
  changes_proof_class: z.literal(false),
})
export const nativeControlComparison = z.discriminatedUnion("available", [
  z.object({ available: z.literal(false), reason: z.string() }),
  z.object({
    available: z.literal(true),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    parser_name: z.string(),
    parser_version: z.string(),
    date_context: z.object({
      earliest: z.string(),
      latest: z.string(),
      basis: z.string(),
    }),
    current: calculation,
    proposed: calculation,
    current_transaction_ids: z.array(z.string()),
    limitation: z.string(),
  }),
])
export type NativeControlComparison = z.infer<typeof nativeControlComparison>
