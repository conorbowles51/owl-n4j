import {
  traceAssetDraw,
  traceAssetResults,
  verifyTraceAssets,
} from "./trace-assets"
import { z } from "zod"

export const methods = [
  "lowest_intermediate_balance",
  "first_in_first_out",
  "last_in_first_out",
  "pro_rata",
  "direct",
] as const
const money = z.object({
  minor_units: z.string().regex(/^-?[0-9]+$/),
  currency: z.string(),
})
export const traceInputs = z
  .object({
    population: z.enum(["working", "verified"]).default("verified"),
    case_id: z.string(),
    account_id: z.string(),
    start_date: z.string(),
    end_date: z.string(),
    currency: z.string(),
    snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    included_rows: z.number().int().positive().max(1000),
    excluded_rows: z.number().int().nonnegative(),
    applied: z.literal(false),
    readings: z
      .array(
        z.object({
          included: z.boolean(),
          exclusion_reason: z.string().nullable().optional(),
          row: z.object({
            key: z.string(),
            ordering_date: z.string(),
            amount_minor: z.string().regex(/^[0-9]+$/),
            direction: z.enum(["credit", "debit"]),
            description: z.string().nullable(),
            currency: z.string(),
          }),
        })
      )
      .max(1000),
  })
  .refine(
    (v) =>
      v.included_rows === v.readings.length &&
      new Set(v.readings.map((r) => r.row.key)).size === v.readings.length &&
      v.readings.every(
        (r) =>
          r.row.currency === v.currency &&
          (r.included ||
            (v.population === "working" &&
              r.exclusion_reason === "proof_class_not_included"))
      )
  )
export type TraceInputs = z.infer<typeof traceInputs>
const scenario = z.object({
  schema: z.literal("loupe.financial.conditional_trace/1"),
  case_id: z.string(),
  account_id: z.string(),
  applied: z.literal(false),
  assumptions_verified: z.literal(false),
  inputs: z.object({ expected_snapshot_sha256: z.string() }).passthrough(),
  limitations: z.array(z.string()),
  asset_uses: z.record(z.string(), traceAssetResults).default({}),
  comparison: z.object({
    results: z.record(
      z.string(),
      z.object({
        outcomes: z.record(
          z.string(),
          z.object({ deposited: money, surviving: money, withdrawn: money })
        ),
        draws: z.array(traceAssetDraw),
        notes: z.array(z.string()),
      })
    ),
  }),
})
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`
  if (value !== null && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`)
      .join(",")}}`
  return JSON.stringify(value)
}
export async function verifyTraceResponse(
  raw: unknown,
  scope: TraceInputs,
  request: Record<string, unknown>
) {
  const envelope = z
    .object({
      case_id: z.string(),
      account_id: z.string(),
      applied: z.literal(false),
      scenario_json: z.string(),
      scenario_sha256: z.string().regex(/^[a-f0-9]{64}$/),
      scenario_byte_count: z
        .number()
        .int()
        .positive()
        .max(16 * 1024 * 1024),
    })
    .parse(raw)
  const bytes = new TextEncoder().encode(envelope.scenario_json)
  const digest = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  if (
    bytes.length !== envelope.scenario_byte_count ||
    digest !== envelope.scenario_sha256
  )
    throw new Error("Scenario download failed its integrity check.")
  const value = scenario.parse(JSON.parse(envelope.scenario_json))
  if (
    [envelope.case_id, value.case_id].some((id) => id !== scope.case_id) ||
    [envelope.account_id, value.account_id].some(
      (id) => id !== scope.account_id
    ) ||
    value.inputs.expected_snapshot_sha256 !== scope.snapshot_sha256 ||
    Object.keys(request).some(
      (key) => canonical(value.inputs[key]) !== canonical(request[key])
    )
  )
    throw new Error("Scenario does not match these inputs and assumptions.")
  if (
    Array.isArray(request.doctrines) &&
    canonical([...request.doctrines].sort()) !==
      canonical(Object.keys(value.comparison.results).sort())
  )
    throw new Error("Scenario returned different calculation methods.")
  for (const [method, result] of Object.entries(value.comparison.results)) {
    verifyTraceAssets(
      value.asset_uses[method] ?? [],
      request.asset_uses,
      scope.readings.map((r) => r.row),
      result.draws,
      request.ordered_transaction_ids
    )
    const amounts = [
      ...Object.values(result.outcomes).flatMap((o) => [
        o.deposited,
        o.surviving,
        o.withdrawn,
      ]),
      ...result.draws.flatMap((d) => [d.unfunded, d.unidentified]),
    ]
    if (amounts.some((m) => m.currency !== scope.currency))
      throw new Error("Scenario returned a different currency.")
    if (
      Object.values(result.outcomes).some(
        (o) =>
          BigInt(o.deposited.minor_units) !==
          BigInt(o.surviving.minor_units) + BigInt(o.withdrawn.minor_units)
      )
    )
      throw new Error("Scenario claim totals do not reconcile.")
  }
  return { envelope, value }
}

export { scenario as traceScenarioSchema }
