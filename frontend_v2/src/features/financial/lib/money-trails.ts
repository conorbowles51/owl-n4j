import { z } from "zod"
import { correctionMoney } from "./correction-contract"
const id = z.string().uuid()
export const trailPreview = z.object({
  case_id: id,
  kind: z.enum(["transfer", "allocation"]),
  input: z.record(z.string(), z.unknown()),
  payments: z.array(
    z
      .object({
        key: id,
        account_id: id,
        source_document_id: id,
        description: z.string().nullable(),
        account_label: z.string().nullable().optional(),
        direction: z.enum(["debit", "credit"]),
        amount_minor: z.string().regex(/^\d+$/),
        currency: z.string(),
        ordering_date: z.string(),
        from_name: z.string().optional(),
        to_name: z.string().optional(),
        ref_id: z.string(),
        running_balance_minor: z.string().nullable(),
        superseded_by_id: z.string().nullable(),
      })
      .passthrough()
  ),
  ownership: z.record(z.string(), z.unknown()),
  common_holders: z.array(z.object({ id, name: z.string() })),
  internal_transfer: z.boolean(),
  implied_exchange_rate: z.string().nullable(),
  receipt_unallocated_minor: z.string().nullable(),
  warnings: z.array(z.string()),
  source_revision: z.string().regex(/^[a-f0-9]{64}$/),
  transfer_breakdown: z
    .object({
      sent_currency: z.string(),
      sent_minor: z.string(),
      received_currency: z.string(),
      received_minor: z.string(),
      fees: z.array(
        z.object({ currency: z.string(), amount_minor: z.string() })
      ),
      entries: z.array(
        z.object({
          transaction_id: id,
          direction: z.enum(["debit", "credit"]),
          currency: z.string(),
          principal_minor: z.string(),
          fee_minor: z.string(),
          original_minor: z.string(),
          unassigned_minor: z.string(),
          remaining_after_other_links_minor: z.string(),
        })
      ),
    })
    .nullable()
    .optional(),
  account_context: z
    .object({
      currency: z.string(),
      opening_balance_minor: z.string().nullable(),
      opening_balance_source: z.string(),
      period_start: z.string().nullable(),
      payment_count: z.number(),
      payments: z.array(
        z
          .object({
            key: id,
            ordering_date: z.string(),
            description: z.string().nullable(),
            ref_id: z.string(),
            direction: z.string(),
            amount_minor: z.string(),
            running_balance_minor: z.string().nullable(),
          })
          .passthrough()
      ),
      sequence_revision: z.string(),
      limitation: z.string(),
    })
    .nullable()
    .optional(),
})
export const savedTrail = z.object({
  id,
  case_id: id,
  kind: z.enum(["transfer", "allocation"]),
  revision: z.number().int().positive(),
  active: z.boolean(),
  status: z.enum(["current", "source_changed", "removed"]),
  details: trailPreview,
  history: z.array(z.unknown()),
  matching_entries: trailPreview.shape.payments.default([]),
  matching_entries_truncated: z.boolean().default(false),
})
export const savedTrails = z.object({
  case_id: id,
  trails: z.array(savedTrail),
})
export type SavedTrail = z.infer<typeof savedTrail>
export type TrailPreview = z.infer<typeof trailPreview>

export function trailNarrative(trail: SavedTrail) {
  const d = trail.details
  return [
    `Saved money trail ${trail.id}, revision ${trail.revision}.`,
    trail.status === "source_changed"
      ? "Source changed — this saved interpretation requires review."
      : "",
    d.kind === "allocation"
      ? "Investigator's onward allocation."
      : d.internal_transfer
        ? `Transfer between accounts with a reviewed common holder: ${d.common_holders.map((p) => p.name).join(", ")}.`
        : "Transfer link; common ownership is not established.",
    ...d.payments.map(
      (p) =>
        `${p.ordering_date} · ${p.account_label || p.account_id} · ${p.direction} · ${correctionMoney(p.amount_minor, p.currency)} · ${p.description || p.ref_id} · source ${p.source_document_id}`
    ),
    ...(d.kind === "allocation"
      ? (
          d.input.payments as { transaction_id: string; amount_minor: string }[]
        ).map(
          (a) =>
            `Allocated ${correctionMoney(a.amount_minor, d.payments.find((p) => p.key === a.transaction_id)!.currency)} to ${d.payments.find((p) => p.key === a.transaction_id)!.ref_id}.`
        )
      : []),
    ...(d.account_context
      ? [
          `Account context: ${d.account_context.payment_count} imported entries in the receipt-to-payment date range. Opening statement balance ${d.account_context.opening_balance_minor === null ? "not recorded" : correctionMoney(d.account_context.opening_balance_minor, d.account_context.currency)}. ${d.account_context.limitation}`,
        ]
      : []),
    ...(d.transfer_breakdown
      ? [
          `Assigned principal: ${correctionMoney(d.transfer_breakdown.sent_minor, d.transfer_breakdown.sent_currency)} sent → ${correctionMoney(d.transfer_breakdown.received_minor, d.transfer_breakdown.received_currency)} received.`,
          ...d.transfer_breakdown.entries.map(
            (p) =>
              `${d.payments.find((row) => row.key === p.transaction_id)?.ref_id}: principal ${correctionMoney(p.principal_minor, p.currency)}; fee ${correctionMoney(p.fee_minor, p.currency)}; unassigned in this link ${correctionMoney(p.unassigned_minor, p.currency)}.`
          ),
        ]
      : []),
    `Basis: ${d.input.reason}`,
    ...d.warnings,
  ]
    .filter(Boolean)
    .join("\n\n")
}

/** Internal principal is counted once; fees and unassigned portions remain external.
 * The account scope is evaluated before search/category filters. */
export function internalActivity(
  rows: { key: string }[],
  trails: SavedTrail[]
) {
  const population = new Set(rows.map((p) => p.key))
  const ids = new Set<string>()
  const movements = new Map<string, bigint>()
  const portions = new Map<string, bigint>()
  let pending = 0
  for (const trail of trails) {
    if (!trail.active || trail.kind !== "transfer") continue
    const payments = trail.details.payments
    if (!payments.some((p) => population.has(p.key))) continue
    const breakdown = trail.details.transfer_breakdown
    const principal = breakdown
      ? breakdown.entries
          .filter((p) => BigInt(p.principal_minor) > 0n)
          .map((part) => ({
            ...payments.find((p) => p.key === part.transaction_id)!,
            principal: BigInt(part.principal_minor),
          }))
      : payments.map((p) => ({ ...p, principal: BigInt(p.amount_minor) }))
    if (
      trail.status !== "current" ||
      !trail.details.internal_transfer ||
      principal.length < 2 ||
      !principal.every((p) => population.has(p.key))
    ) {
      pending++
      continue
    }
    for (const p of principal)
      portions.set(p.key, (portions.get(p.key) || 0n) + p.principal)
    const sameCurrency = new Set(principal.map((p) => p.currency)).size === 1
    for (const p of principal) {
      if (sameCurrency && p.direction !== "debit") continue
      const unit = sameCurrency
        ? p.currency
        : `${p.currency} ${p.direction === "debit" ? "sent" : "received"}`
      movements.set(unit, (movements.get(unit) || 0n) + p.principal)
    }
  }
  for (const [key, amount] of portions) if (amount > 0n) ids.add(key)
  return { ids, movements, portions, pending }
}

export function activityAmount(
  row: { key: string; amount_minor: string | number },
  activity: string,
  internal: ReturnType<typeof internalActivity>
) {
  const full = BigInt(row.amount_minor),
    principal = internal.portions.get(row.key) || 0n
  return activity === "internal"
    ? principal
    : activity === "external"
      ? full - principal
      : full
}
