import { z } from "zod"
import { currencyMinorUnits } from "./ledger-format"

const integer = z.string().regex(/^-?(0|[1-9][0-9]*)$/)
const magnitude = z
  .string()
  .regex(/^(0|[1-9][0-9]{0,18})$/)
  .refine(
    (value) =>
      /^[0-9]{1,19}$/.test(value) && BigInt(value) <= 9223372036854775807n,
    "Amount is outside the ledger range"
  )
const direction = z.enum(["credit", "debit"])
const proof = z.enum(["p0", "p1", "p2", "p3"])
const identity = z.object({
  status: z.string(),
  delta_minor: integer.nullable(),
})
const balanceWalk = z
  .object({
    compared_intervals: z.number().int().nonnegative(),
    mismatch_count: z.number().int().nonnegative(),
    unanchored_balances: z.number().int().nonnegative(),
    excluded_rows: z.number().int().nonnegative(),
    trailing_rows_without_balance: z.number().int().nonnegative(),
    findings_truncated: z.boolean(),
    findings: z
      .array(
        z.object({
          before_ref: z.string().nullable(),
          after_ref: z.string(),
          after_transaction_id: z.string(),
          expected_minor: integer,
          printed_minor: integer,
          delta_minor: integer,
        })
      )
      .max(100),
  })
  .refine(
    (v) =>
      v.mismatch_count <= v.compared_intervals &&
      v.findings.length <= v.mismatch_count
  )
export const runningBalanceComparison = z.discriminatedUnion("available", [
  z.object({
    available: z.literal(false),
    reason: z.string(),
    interpretations: z.array(z.never()).length(0),
  }),
  z.object({
    available: z.literal(true),
    reason: z.null(),
    currency: z.string(),
    limitation: z.string(),
    interpretations: z
      .array(
        z.object({
          order: z.enum(["source_row_order", "reverse_source_row_order"]),
          current: balanceWalk,
          proposed: balanceWalk,
        })
      )
      .length(2)
      .refine((v) => new Set(v.map((i) => i.order)).size === 2),
  }),
])
export type RunningBalanceComparison = z.infer<typeof runningBalanceComparison>
export const currentRunningBalanceComparison = z.discriminatedUnion(
  "available",
  [
    runningBalanceComparison.options[0],
    runningBalanceComparison.options[1].extend({
      interpretations: z
        .array(
          z.object({
            order: z.enum(["source_row_order", "reverse_source_row_order"]),
            current: balanceWalk,
          })
        )
        .length(2)
        .refine((v) => new Set(v.map((i) => i.order)).size === 2),
    }),
  ]
)
export type CurrentRunningBalanceComparison = z.infer<
  typeof currentRunningBalanceComparison
>
export const correctionPreview = z.object({
  case_id: z.string(),
  transaction_id: z.string(),
  document_revision: z.string().regex(/^[a-f0-9]{64}$/),
  applied: z.literal(false),
  original: z.object({
    key: z.string(),
    ref_id: z.string(),
    source_document_id: z.string(),
    amount_minor: magnitude,
    currency: z.string(),
    direction,
  }),
  proposed: z.object({
    amount_minor: magnitude,
    currency: z.string(),
    direction,
    ledger_status: z.enum(["admitted", "quarantined"]),
  }),
  running_balances: runningBalanceComparison.optional(),
  statement_identity: z
    .object({ current: identity, proposed: identity })
    .nullable(),
  limitation: z.string(),
  verification: z
    .object({
      can_record: z.boolean(),
      current_proof_class: proof,
      proposed_proof_class: proof.nullable(),
      reservations: z.array(z.string()),
      included_in_default_totals: z.boolean(),
      scope: z.string(),
      reason: z.string().nullable(),
    })
    .refine((value) => {
      if (!value.can_record)
        return (
          value.proposed_proof_class === null &&
          !value.included_in_default_totals &&
          Boolean(value.reason?.trim())
        )
      if (value.proposed_proof_class === null || value.reason !== null)
        return false
      const eligible = value.proposed_proof_class !== "p3"
      return (
        value.included_in_default_totals === eligible &&
        (!eligible || value.reservations.length === 0)
      )
    }, "Correction verification is inconsistent"),
})
export type CorrectionPreview = z.infer<typeof correctionPreview>
export const correctionAnswer = z.object({
  case_id: z.string(),
  transaction_id: z.string(),
  replacement_id: z.string().min(1),
  replacement_ref_id: z.string().min(1),
  adjudication_id: z.string().min(1),
  applied: z.literal(true),
  proof_class: proof,
  ledger_status: z.enum(["admitted", "quarantined"]),
})

export function correctionMinor(
  value: string,
  currency: string
): string | null {
  const scale = currencyMinorUnits(currency)
  if (scale === null || !/^\d+(\.\d+)?$/.test(value.trim())) return null
  const [whole, fraction = ""] = value.trim().split(".")
  if (fraction.length > scale) return null
  const minor = BigInt(whole + fraction.padEnd(scale, "0"))
  return minor <= 9223372036854775807n ? String(minor) : null
}

export function correctionMoney(minor: string, currency: string): string {
  const scale = currencyMinorUnits(currency)
  if (scale === null) return `${minor} minor units (${currency})`
  const negative = minor.startsWith("-")
  const digits = (negative ? minor.slice(1) : minor).padStart(scale + 1, "0")
  const value =
    scale === 0 ? digits : `${digits.slice(0, -scale)}.${digits.slice(-scale)}`
  return `${negative ? "-" : ""}${value} ${currency}`
}
