import { sha256Hex } from "@/lib/browser-crypto"
import { z } from "zod"
const money = z.object({
  minor_units: z.string().regex(/^-?\d+$/),
  currency: z.string(),
})
export const claimComparison = z.object({
  schema: z.literal("loupe.financial.claim_comparison/1"),
  case_id: z.string(),
  applied: z.literal(false),
  claim_proof_class: z.literal("p4"),
  inputs: z.record(z.string(), z.unknown()),
  claim_source: z.object({
    id: z.string(),
    case_id: z.string(),
    filename: z.string(),
    sha256: z.string().nullable(),
  }),
  snapshot_sha256: z.string(),
  date_unavailable_ids: z.array(z.string()),
  limitations: z.array(z.string()),
  comparison: z.object({
    outcome: z.enum(["corroborated", "unresolved"]),
    unresolved_reason: z.string().nullable(),
    tolerance: money,
    notes: z.array(z.string()),
    candidates: z.array(
      z.object({
        verdict: z.string(),
        entry: z.object({
          transaction_id: z.string(),
          account_id: z.string(),
          ordering_date: z.string(),
          chronology_basis: z.string(),
          amount: money,
          direction: z.string(),
          proof_class: z.string(),
          description: z.string().nullable(),
          reconciled: z.null(),
        }),
        components: z.record(
          z.string(),
          z.object({
            name: z.string(),
            agreement: z.string(),
            detail: z.string(),
          })
        ),
      })
    ),
  }),
})
export async function verifyClaimComparison(
  raw: unknown,
  caseId: string,
  request: Record<string, unknown>
) {
  const envelope = z
    .object({
      case_id: z.string(),
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
  const bytes = new TextEncoder().encode(envelope.scenario_json),
    hash = await sha256Hex(bytes)
  if (
    hash !== envelope.scenario_sha256 ||
    bytes.length !== envelope.scenario_byte_count
  )
    throw Error("Claim comparison failed its integrity check.")
  const value = claimComparison.parse(JSON.parse(envelope.scenario_json))
  if (
    envelope.case_id !== caseId ||
    value.case_id !== caseId ||
    value.claim_source.case_id !== caseId ||
    value.claim_source.id !== request.source_file_id ||
    Object.keys(request).some(
      (k) => JSON.stringify(value.inputs[k]) !== JSON.stringify(request[k])
    )
  )
    throw Error("Claim comparison differs from the selected inputs.")
  if (
    value.comparison.tolerance.currency !== request.currency ||
    value.comparison.candidates.some(
      (c) =>
        c.entry.account_id !== request.account_id ||
        (request.population === "verified" &&
          !["p0", "p1", "p2"].includes(c.entry.proof_class))
    )
  )
    throw Error(
      "Comparison readings differ from the selected account or population."
    )
  return { envelope, value }
}

export type VerifiedClaimComparison = Awaited<
  ReturnType<typeof verifyClaimComparison>
>
