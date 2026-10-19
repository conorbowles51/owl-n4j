import { z } from "zod"
import { correctionMinor } from "./correction-contract"
export const controlCell = z.object({
  page_number: z.number().int().positive(),
  table_index: z.number().int().nonnegative(),
  row_index: z.number().int().nonnegative(),
  column_index: z.number().int().nonnegative(),
  source_revision: z.string().regex(/^[a-f0-9]{64}$/),
  expected_text: z.string().min(1).max(4096),
})
const dateControl = z.object({
  value: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .refine((value) => {
      const time = Date.parse(value + "T00:00:00Z")
      return (
        Number.isFinite(time) &&
        new Date(time).toISOString().slice(0, 10) === value
      )
    }),
  source: controlCell,
})
const balanceControl = z.object({
  amount_minor: z
    .string()
    .regex(/^-?(0|[1-9][0-9]{0,18})$/)
    .refine(
      (v) =>
        BigInt(v) >= -9223372036854775808n && BigInt(v) <= 9223372036854775807n
    ),
  source: controlCell,
})
export const statementScope = z
  .object({
    account_id: z.string().uuid(),
    currency: z.string().length(3),
    candidate_ids: z.array(z.string().uuid()).min(1).max(1000),
    start: dateControl,
    end: dateControl,
    opening: balanceControl.nullable(),
    closing: balanceControl.nullable(),
    credits_total: balanceControl
      .refine((v) => BigInt(v.amount_minor) >= 0n)
      .optional(),
    debits_total: balanceControl
      .refine((v) => BigInt(v.amount_minor) >= 0n)
      .optional(),
    balance_convention: z.enum(["asset_balance", "liability_owed"]),
    reason: z.string().trim().min(1).max(4096),
  })
  .refine(
    (v) =>
      v.start.value <= v.end.value &&
      new Set(v.candidate_ids).size === v.candidate_ids.length
  )
export type StatementScope = z.infer<typeof statementScope>
export type ControlCell = z.infer<typeof controlCell>
export const scopeReading = z.object({
  candidate_id: z.string(),
  account_id: z.string(),
  currency: z.string(),
  account_label: z.string(),
  booking_date: z.string().nullable(),
  transaction_date: z.string().nullable(),
  description: z.string().nullable(),
})
export type ScopeReading = z.infer<typeof scopeReading>
export function signedControlMinor(value: string, currency: string) {
  const negative = value.startsWith("-")
  const minor = correctionMinor(negative ? value.slice(1) : value, currency)
  return minor === null ? null : negative && minor !== "0" ? `-${minor}` : minor
}
