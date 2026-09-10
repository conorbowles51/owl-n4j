import { z } from "zod"
const minor = z.string().regex(/^(0|[1-9][0-9]*)$/)
const money = z.object({ minor_units: minor, currency: z.string() })
export interface TraceAssetUse {
  transaction_id: string
  asset_label: string
  basis: string
}
export const traceAssetDraw = z.object({
  transaction_id: z.string().optional(),
  amount: money.optional(),
  by_claim: z.record(z.string(), money).default({}),
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
      asset.unidentified_minor !== draw.unidentified.minor_units ||
      asset.unfunded_minor !== draw.unfunded.minor_units ||
      Object.keys(asset.allocated_by_claim).length !==
        Object.keys(draw.by_claim).length ||
      Object.entries(asset.allocated_by_claim).some(
        ([claim, amount]) =>
          draw.by_claim[claim]?.minor_units !== amount ||
          draw.by_claim[claim].currency !== row.currency
      ) ||
      Object.values(asset.allocated_by_claim).reduce(
        (n, a) => n + BigInt(a),
        0n
      ) +
        BigInt(asset.outside_claims_minor) !==
        BigInt(row.amount_minor)
    )
      throw Error("Asset allocation differs from its source withdrawal.")
  }
}
