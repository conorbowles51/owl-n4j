import { correctionMinor } from "./correction-contract"
import { z } from "zod"
const minor = z.string().regex(/^(0|-?[1-9][0-9]*)$/)
const methodId = z.enum(["net_worth", "bank_deposits", "expenditure", "cash_t"])
export const indirectCatalog = z.object({
  case_id: z.string().uuid(),
  reference: z.string().url(),
  methods: z.array(
    z.object({
      id: methodId,
      label: z.string(),
      reference_section: z.string(),
      terms: z.array(
        z.object({
          id: z.string(),
          label: z.string(),
          sign: z.union([z.literal(1), z.literal(-1)]),
          signed: z.boolean(),
        })
      ),
    })
  ),
  requirements: z.array(z.object({ id: z.string(), label: z.string() })),
})
export type IndirectCatalog = z.infer<typeof indirectCatalog>
const reference = {
  basis: z.string(),
  source_file_id: z.string().uuid().nullable(),
  source_location: z.string(),
}
const entry = z.object({ amount_minor: minor.nullable(), ...reference })
const requirement = z.object({
  status: z.enum(["reviewed", "unresolved"]),
  ...reference,
})
export const indirectRequest = z.object({
  method: methodId,
  currency: z.string().regex(/^[A-Z]{3}$/),
  start_date: z.string(),
  end_date: z.string(),
  subject: z.string(),
  entries: z.record(z.string(), entry),
  requirements: z.record(z.string(), requirement),
})
export type IndirectRequest = z.infer<typeof indirectRequest>
export const indirectEnvelope = z.object({
  case_id: z.string().uuid(),
  applied: z.literal(false),
  scenario_json: z.string(),
  scenario_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  scenario_byte_count: z.number().int().positive(),
})
const indirectValue = z.object({
  schema: z.literal("loupe.financial.indirect_review/1"),
  case_id: z.string().uuid(),
  applied: z.literal(false),
  reference: z.string().url(),
  reference_section: z.string(),
  inputs: indirectRequest,
  method_label: z.string(),
  lines: z.array(
    entry.extend({
      id: z.string(),
      label: z.string(),
      sign: z.union([z.literal(1), z.literal(-1)]),
    })
  ),
  sources: z.array(
    z.object({
      id: z.string().uuid(),
      case_id: z.string().uuid(),
      filename: z.string(),
      sha256: z.string().nullable(),
    })
  ),
  missing: z.array(
    z.object({
      kind: z.enum(["amount", "review"]),
      id: z.string(),
      label: z.string(),
    })
  ),
  review_fields_complete: z.boolean(),
  difference_minor: minor.nullable(),
  limitation: z.string(),
})
const canonical = (v: unknown): string =>
  Array.isArray(v)
    ? `[${v.map(canonical).join(",")}]`
    : v && typeof v === "object"
      ? `{${Object.entries(v)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`)
          .join(",")}}`
      : JSON.stringify(v)
export async function verifyIndirectReview(
  raw: unknown,
  catalog: IndirectCatalog,
  request: IndirectRequest
) {
  const envelope = indirectEnvelope.parse(raw),
    bytes = new TextEncoder().encode(envelope.scenario_json)
  const digest = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  if (
    envelope.case_id !== catalog.case_id ||
    bytes.length !== envelope.scenario_byte_count ||
    digest !== envelope.scenario_sha256
  )
    throw Error("Workpaper capture failed its integrity check.")
  const value = indirectValue.parse(JSON.parse(envelope.scenario_json)),
    method = catalog.methods.find((m) => m.id === request.method)
  if (
    !method ||
    value.case_id !== catalog.case_id ||
    canonical(value.inputs) !== canonical(request) ||
    value.method_label !== method.label ||
    value.reference !== catalog.reference ||
    value.reference_section !== method.reference_section
  )
    throw Error("Workpaper differs from the requested scope.")
  const sourceIds = [
    ...new Set(
      [
        ...Object.values(request.entries),
        ...Object.values(request.requirements),
      ].flatMap((r) => (r.source_file_id ? [r.source_file_id] : []))
    ),
  ].sort()
  if (
    value.sources.some((s) => s.case_id !== catalog.case_id) ||
    canonical(value.sources.map((s) => s.id).sort()) !== canonical(sourceIds)
  )
    throw Error("Workpaper source scope differs.")
  const missing: { kind: string; id: string; label: string }[] = []
  let total = 0n
  if (value.lines.length !== method.terms.length)
    throw Error("Workpaper omitted an amount field.")
  for (const [i, term] of method.terms.entries()) {
    const line = value.lines[i],
      input = request.entries[term.id]
    if (
      !input ||
      canonical(line) !==
        canonical({ ...input, id: term.id, label: term.label, sign: term.sign })
    )
      throw Error("Workpaper amount field differs.")
    if (input.amount_minor !== null) {
      if (!term.signed && BigInt(input.amount_minor) < 0n)
        throw Error("Invalid amount sign.")
      total += BigInt(term.sign) * BigInt(input.amount_minor)
    }
    if (
      input.amount_minor === null ||
      !input.basis.trim() ||
      !input.source_file_id ||
      !input.source_location.trim()
    )
      missing.push({ kind: "amount", id: term.id, label: term.label })
  }
  for (const check of catalog.requirements) {
    const input = request.requirements[check.id]
    if (
      !input ||
      input.status !== "reviewed" ||
      !input.basis.trim() ||
      !input.source_file_id ||
      !input.source_location.trim()
    )
      missing.push({ kind: "review", id: check.id, label: check.label })
  }
  if (
    canonical(value.missing) !== canonical(missing) ||
    value.review_fields_complete !== (missing.length === 0) ||
    value.difference_minor !== (missing.length ? null : String(total))
  )
    throw Error("Workpaper completeness or arithmetic differs.")
  return { envelope, value }
}
export type VerifiedIndirectReview = Awaited<
  ReturnType<typeof verifyIndirectReview>
>

export function indirectMinor(
  value: string,
  currency: string,
  signed: boolean
): string | null {
  const text = value.trim(),
    negative = text.startsWith("-")
  if (negative && !signed) return null
  const amount = correctionMinor(negative ? text.slice(1) : text, currency)
  return amount === null
    ? null
    : negative && amount !== "0"
      ? `-${amount}`
      : amount
}
