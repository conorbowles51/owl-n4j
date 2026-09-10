import { z } from "zod"
const money = z.string().regex(/^(0|[1-9][0-9]*)$/)
const count = z.number().int().nonnegative()
const row = z.object({
  key: z.string(),
  case_id: z.string(),
  account_id: z.string(),
  account_label: z.string().optional(),
  counterparty_raw: z.string().nullable().optional(),
  source_document_id: z.string(),
  amount_minor: money,
  currency: z.string(),
  direction: z.enum(["credit", "debit"]),
  ordering_date: z.string(),
  description: z.string().nullable(),
})
export const transferInputs = z
  .object({
    case_id: z.string(),
    start_date: z.string().nullable(),
    end_date: z.string().nullable(),
    population: z.enum(["working", "verified"]),
    tolerance_days: count.max(7),
    snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    applied: z.literal(false),
    limitation: z.string(),
    excluded_rows: count,
    rows: z.array(row).max(500),
    date_unavailable_ids: z.array(z.string()),
    candidates: z
      .array(
        z.object({
          debit_id: z.string(),
          credit_id: z.string(),
          currency: z.string(),
          amount_minor: money,
          outcome: z.enum(["resolved", "ambiguous"]),
          date_gap_days: count.nullable(),
          compared_date_field: z.string().nullable(),
        })
      )
      .max(1000),
  })
  .superRefine((data, ctx) => {
    const rows = new Map(data.rows.map((r) => [r.key, r]))
    const pairs = new Set<string>()
    if (
      rows.size !== data.rows.length ||
      data.rows.some((r) => r.case_id !== data.case_id)
    )
      ctx.addIssue({
        code: "custom",
        message: "Reading scope is inconsistent.",
      })
    for (const p of data.candidates) {
      const d = rows.get(p.debit_id),
        c = rows.get(p.credit_id),
        key = `${p.debit_id}:${p.credit_id}`
      if (
        !d ||
        !c ||
        d.direction !== "debit" ||
        c.direction !== "credit" ||
        d.account_id === c.account_id ||
        d.currency !== p.currency ||
        c.currency !== p.currency ||
        d.amount_minor !== p.amount_minor ||
        c.amount_minor !== p.amount_minor ||
        pairs.has(key)
      )
        ctx.addIssue({
          code: "custom",
          message: "Transfer candidate does not match its source readings.",
        })
      pairs.add(key)
    }
  })
export type TransferInputs = z.infer<typeof transferInputs>
const figures = z.array(
  z.object({
    currency: z.string(),
    posting_rows: count,
    paired_transfers: count,
    movement_count: count,
    paired_amount_minor: money,
    unpaired_credits_minor: money,
    unpaired_debits_minor: money,
    movement_volume_minor: money,
  })
)
export async function verifyTransferScenario(
  raw: unknown,
  scope: TransferInputs,
  request: Record<string, unknown>
) {
  const result = z
    .object({
      case_id: z.string(),
      applied: z.literal(false),
      figures,
      scenario_json: z.string(),
      scenario_sha256: z.string().regex(/^[a-f0-9]{64}$/),
      scenario_byte_count: count.max(16 * 1024 * 1024),
    })
    .parse(raw)
  const bytes = new TextEncoder().encode(result.scenario_json)
  const hash = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  if (
    hash !== result.scenario_sha256 ||
    bytes.length !== result.scenario_byte_count
  )
    throw Error("Transfer report failed its integrity check.")
  const saved = z
    .object({
      schema: z.literal("loupe.financial.transfer_scenario/1"),
      case_id: z.string(),
      applied: z.literal(false),
      pairings_verified: z.literal(false),
      inputs: z.record(z.string(), z.unknown()),
      figures,
    })
    .parse(JSON.parse(result.scenario_json))
  function canonical(v: unknown): string {
    if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`
    if (v && typeof v === "object")
      return `{${Object.entries(v)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`)
        .join(",")}}`
    return JSON.stringify(v)
  }
  if (
    result.case_id !== scope.case_id ||
    saved.case_id !== scope.case_id ||
    Object.keys(request).some(
      (k) => canonical(request[k]) !== canonical(saved.inputs[k])
    ) ||
    canonical(saved.figures) !== canonical(result.figures)
  )
    throw Error(
      "Transfer report does not match the selected scope and assumptions."
    )
  const choices = z
    .array(z.object({ debit_id: z.string(), credit_id: z.string() }))
    .min(1)
    .max(250)
    .parse(request.pairs)
  const used = new Set<string>()
  const expected = new Map<
    string,
    {
      rows: number
      credits: bigint
      debits: bigint
      paired: bigint
      pairs: number
    }
  >()
  for (const row of scope.rows) {
    const group = expected.get(row.currency) ?? {
      rows: 0,
      credits: 0n,
      debits: 0n,
      paired: 0n,
      pairs: 0,
    }
    group.rows++
    if (row.direction === "credit") group.credits += BigInt(row.amount_minor)
    else group.debits += BigInt(row.amount_minor)
    expected.set(row.currency, group)
  }
  for (const choice of choices) {
    const pair = scope.candidates.find(
      (p) => p.debit_id === choice.debit_id && p.credit_id === choice.credit_id
    )
    if (!pair || used.has(choice.debit_id) || used.has(choice.credit_id))
      throw Error(
        "Transfer report repeats a reading or uses an unproposed pair."
      )
    used.add(choice.debit_id)
    used.add(choice.credit_id)
    const group = expected.get(pair.currency)!
    group.paired += BigInt(pair.amount_minor)
    group.pairs++
  }
  if (
    result.figures.length !== expected.size ||
    new Set(result.figures.map((f) => f.currency)).size !== expected.size
  )
    throw Error(
      "Transfer report currency groups differ from the selected readings."
    )
  for (const f of result.figures) {
    const group = expected.get(f.currency)
    if (
      !group ||
      f.posting_rows !== group.rows ||
      f.paired_transfers !== group.pairs ||
      BigInt(f.paired_amount_minor) !== group.paired ||
      BigInt(f.unpaired_credits_minor) !== group.credits - group.paired ||
      BigInt(f.unpaired_debits_minor) !== group.debits - group.paired
    )
      throw Error(
        "Transfer report totals differ from the selected source readings."
      )
  }
  for (const f of result.figures) {
    if (
      f.movement_count !== f.posting_rows - f.paired_transfers ||
      BigInt(f.movement_volume_minor) !==
        BigInt(f.unpaired_credits_minor) +
          BigInt(f.unpaired_debits_minor) +
          BigInt(f.paired_amount_minor)
    )
      throw Error("Transfer figures do not reconcile.")
  }
  return result
}
