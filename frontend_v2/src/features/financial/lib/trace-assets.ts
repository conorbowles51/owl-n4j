import { z } from "zod"
const minor = z.string().regex(/^(0|[1-9][0-9]*)$/)
const money = z.object({ minor_units: minor, currency: z.string() })
export interface TraceAssetUse {
  transaction_id: string
  asset_label: string
  basis: string
  asset_amount_input?: string
}
export const traceAssetDraw = z.object({
  transaction_id: z.string().optional(),
  amount: money.optional(),
  by_claim: z.record(z.string(), money).default({}),
  from_untainted: money.optional(),
  from_opening: money.optional(),
  unidentified: money,
  unfunded: money,
})
export const traceAssetResults = z
  .array(
    z.object({
      transaction_id: z.string(),
      asset_label: z.string(),
      basis: z.string(),
      amount_minor: minor,
      asset_amount_minor: minor.optional(),
      remaining_withdrawal_minor: minor.optional(),
      allocation_basis: z
        .enum(["whole_withdrawal", "proportional_share"])
        .optional(),
      rounding_rule: z.string().optional(),
      currency: z.string(),
      allocated_by_claim: z.record(z.string(), minor),
      outside_claims_minor: minor,
      unidentified_minor: minor,
      unfunded_minor: minor,
      changes_cash_results: z.literal(false),
      limitation: z.string(),
    })
  )
  .max(50)
export type TraceAssetResults = z.infer<typeof traceAssetResults>
export function verifyTraceAssets(
  actual: TraceAssetResults,
  requested: unknown,
  rows: Array<{
    key: string
    direction: string
    amount_minor: string
    currency: string
  }>,
  draws: z.infer<typeof traceAssetDraw>[]
) {
  const uses = z
    .array(
      z.object({
        transaction_id: z.string(),
        asset_label: z.string(),
        basis: z.string(),
        asset_amount_minor: minor.nullable().optional(),
        allocation_basis: z.literal("proportional_share").optional(),
      })
    )
    .max(50)
    .parse(requested ?? [])
  if (
    actual.length !== uses.length ||
    new Set(uses.map((u) => u.transaction_id)).size !== uses.length
  )
    throw Error("Asset interpretation scope differs.")
  for (const [i, asset] of actual.entries()) {
    const use = uses[i],
      row = rows.find((r) => r.key === use.transaction_id),
      draw = draws.find((d) => d.transaction_id === use.transaction_id)
    const partial = use.asset_amount_minor != null
    let claims = Object.fromEntries(
      Object.entries(draw?.by_claim ?? {}).map(([claim, amount]) => [
        claim,
        amount.minor_units,
      ])
    )
    let unidentified = draw?.unidentified.minor_units,
      unfunded = draw?.unfunded.minor_units
    const assetAmount = use.asset_amount_minor ?? row?.amount_minor
    if (partial) {
      if (
        !row ||
        !draw?.from_untainted ||
        !draw.from_opening ||
        use.allocation_basis !== "proportional_share" ||
        BigInt(use.asset_amount_minor!) <= 0n ||
        BigInt(use.asset_amount_minor!) > BigInt(row.amount_minor) ||
        draw.from_untainted.currency !== row.currency ||
        draw.from_opening.currency !== row.currency
      )
        throw Error("Invalid partial asset assumption.")
      const keys = Object.keys(claims).sort(unicodeOrder)
      const weights = [
        ...keys.map((k) => BigInt(claims[k])),
        BigInt(draw.from_untainted.minor_units),
        BigInt(draw.from_opening.minor_units),
        BigInt(draw.unidentified.minor_units),
        BigInt(draw.unfunded.minor_units),
      ]
      if (weights.reduce((n, v) => n + v, 0n) !== BigInt(row.amount_minor))
        throw Error("Withdrawal components do not conserve the source amount.")
      const parts = proportionalParts(BigInt(use.asset_amount_minor!), weights)
      claims = Object.fromEntries(keys.map((key, i) => [key, String(parts[i])]))
      unidentified = String(parts.at(-2))
      unfunded = String(parts.at(-1))
    } else if (use.allocation_basis)
      throw Error("Partial allocation is missing its amount.")
    if (
      (partial || asset.asset_amount_minor !== undefined) &&
      (asset.asset_amount_minor !== assetAmount ||
        asset.remaining_withdrawal_minor !==
          String(
            BigInt(row?.amount_minor ?? "0") - BigInt(assetAmount ?? "0")
          ) ||
        asset.allocation_basis !==
          (partial ? "proportional_share" : "whole_withdrawal"))
    )
      throw Error("Asset portion differs from its requested source amount.")
    if (
      !row ||
      !draw ||
      row.direction !== "debit" ||
      BigInt(row.amount_minor) <= 0n ||
      draw.unidentified.currency !== row.currency ||
      draw.unfunded.currency !== row.currency ||
      BigInt(asset.unidentified_minor) + BigInt(asset.unfunded_minor) >
        BigInt(asset.outside_claims_minor) ||
      asset.transaction_id !== use.transaction_id ||
      asset.asset_label !== use.asset_label ||
      asset.basis !== use.basis ||
      asset.amount_minor !== row.amount_minor ||
      asset.currency !== row.currency ||
      draw.amount?.minor_units !== row.amount_minor ||
      draw.amount.currency !== row.currency ||
      asset.unidentified_minor !== unidentified ||
      asset.unfunded_minor !== unfunded ||
      Object.keys(asset.allocated_by_claim).length !==
        Object.keys(draw.by_claim).length ||
      Object.entries(asset.allocated_by_claim).some(
        ([claim, amount]) =>
          claims[claim] !== amount ||
          draw.by_claim[claim].currency !== row.currency
      ) ||
      Object.values(asset.allocated_by_claim).reduce(
        (n, a) => n + BigInt(a),
        0n
      ) +
        BigInt(asset.outside_claims_minor) !==
        BigInt(assetAmount ?? "0")
    )
      throw Error("Asset allocation differs from its source withdrawal.")
  }
}

// Match Python's code-point ordering for deterministic allocation tie breaks.
function unicodeOrder(a: string, b: string) {
  const aa = Array.from(a, (c) => c.codePointAt(0)!),
    bb = Array.from(b, (c) => c.codePointAt(0)!)
  for (let i = 0; i < Math.min(aa.length, bb.length); i++)
    if (aa[i] !== bb[i]) return aa[i] - bb[i]
  return aa.length - bb.length
}
function proportionalParts(amount: bigint, weights: bigint[]) {
  const total = weights.reduce((n, v) => n + v, 0n)
  if (total <= 0n) throw Error("No withdrawal components available.")
  const parts = weights.map((w) => (amount * w) / total)
  const remainder = amount - parts.reduce((n, v) => n + v, 0n)
  const order = weights
    .map((w, i) => ({ i, remainder: (amount * w) % total }))
    .sort((a, b) =>
      a.remainder === b.remainder
        ? a.i - b.i
        : a.remainder > b.remainder
          ? -1
          : 1
    )
  for (let i = 0n; i < remainder; i++) parts[order[Number(i)].i] += 1n
  return parts
}
