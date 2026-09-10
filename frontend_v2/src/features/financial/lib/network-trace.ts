import { z } from "zod"
import { transferInputs } from "./ledger-transfers"
export const networkInputs = transferInputs.and(
  z.object({
    accounts: z.array(
      z.object({
        account_id: z.string(),
        currency: z.string(),
        label: z.string(),
      })
    ),
    network_row_limit: z.number().int().positive(),
    network_limitation: z.string(),
  })
)
export type NetworkInputs = z.infer<typeof networkInputs>
const minor = z.string().regex(/^(0|[1-9][0-9]*)$/),
  money = z.object({
    minor_units: z.string().regex(/^-?(0|[1-9][0-9]*)$/),
    currency: z.string(),
  })
const resultSchema = z.object({
  schema: z.literal("loupe.financial.network_trace/1"),
  case_id: z.string(),
  applied: z.literal(false),
  assumptions_verified: z.literal(false),
  backward_timing_used: z.boolean().default(false),
  calculation_account_order: z.array(z.string()).default([]),
  inputs: z.record(z.string(), z.unknown()),
  limitations: z.array(z.string()),
  results: z.record(
    z.string(),
    z.object({
      accounts: z.record(
        z.string(),
        z.object({
          currency: z.string(),
          closing_balance: money,
          lowest_balance: money,
          outcomes: z.record(
            z.string(),
            z.object({ deposited: money, surviving: money, withdrawn: money })
          ),
          notes: z.array(z.string()),
        })
      ),
      hops: z.array(
        z.object({
          backward_timing: z.boolean().default(false),
          debit_id: z.string(),
          credit_id: z.string(),
          from_account: z.string(),
          to_account: z.string(),
          amount_minor: minor,
          propagated_by_claim: z.record(z.string(), minor),
          unattributed_or_unidentified_minor: minor,
          unidentified_minor: minor,
          unfunded_minor: minor,
        })
      ),
      claims: z.record(
        z.string(),
        z.object({
          root_attributed_minor: minor,
          reported_remaining_minor: minor,
          withdrawn_without_selected_transfer_minor: minor,
        })
      ),
      unidentified_withdrawals_minor: minor,
    })
  ),
})
function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`
  if (v && typeof v === "object")
    return `{${Object.entries(v)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`)
      .join(",")}}`
  return JSON.stringify(v)
}
export async function verifyNetworkTrace(
  raw: unknown,
  scope: NetworkInputs,
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
    hash = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      (b) => b.toString(16).padStart(2, "0")
    ).join("")
  if (
    hash !== envelope.scenario_sha256 ||
    bytes.length !== envelope.scenario_byte_count
  )
    throw Error("Cross-account report failed its integrity check.")
  const value = resultSchema.parse(JSON.parse(envelope.scenario_json))
  if (
    envelope.case_id !== scope.case_id ||
    value.case_id !== scope.case_id ||
    request.expected_snapshot_sha256 !== scope.snapshot_sha256 ||
    Object.keys(request).some(
      (k) => canonical(value.inputs[k]) !== canonical(request[k])
    )
  )
    throw Error("Cross-account result differs from the selected inputs.")
  const methods = z.array(z.string()).parse(request.doctrines),
    currency = z.string().parse(request.currency),
    openings = z
      .array(z.object({ account_id: z.string() }))
      .parse(request.openings),
    pairs = z
      .array(z.object({ debit_id: z.string(), credit_id: z.string() }))
      .parse(request.pairs),
    attributions = z
      .array(z.object({ claim_id: z.string(), amount_minor: minor }))
      .parse(request.attributions)
  if (
    canonical([...methods].sort()) !==
    canonical(Object.keys(value.results).sort())
  )
    throw Error("Different tracing methods returned.")
  const ordered = z.array(z.string()).parse(request.ordered_transaction_ids)
  const backward = (d: string, c: string) =>
    ordered.indexOf(c) <= ordered.indexOf(d)
  const expectedBackward = pairs.some((p) => backward(p.debit_id, p.credit_id))
  if (
    new Set(ordered).size !== ordered.length ||
    ordered.length !==
      scope.rows.filter((r) => r.currency === currency).length ||
    scope.rows
      .filter((r) => r.currency === currency)
      .some((r) => !ordered.includes(r.key)) ||
    value.backward_timing_used !== expectedBackward ||
    (expectedBackward &&
      (request.allow_backward !== true ||
        typeof request.backward_basis !== "string" ||
        !request.backward_basis.trim()))
  )
    throw Error("Backward timing differs from the explicit assumptions.")
  if (
    expectedBackward &&
    canonical([...value.calculation_account_order].sort()) !==
      canonical(openings.map((o) => o.account_id).sort())
  )
    throw Error("Backward calculation account order differs.")
  const roots = new Map<string, bigint>()
  attributions.forEach((a) =>
    roots.set(
      a.claim_id,
      (roots.get(a.claim_id) ?? 0n) + BigInt(a.amount_minor)
    )
  )
  for (const result of Object.values(value.results)) {
    if (
      canonical(openings.map((o) => o.account_id).sort()) !==
        canonical(Object.keys(result.accounts).sort()) ||
      canonical([...roots.keys()].sort()) !==
        canonical(Object.keys(result.claims).sort())
    )
      throw Error("Cross-account scope differs.")
    for (const [claim, amount] of roots) {
      const c = result.claims[claim]
      const accountRemaining = Object.values(result.accounts).reduce(
        (n, a) => n + BigInt(a.outcomes[claim]?.surviving.minor_units ?? "0"),
        0n
      )
      if (
        BigInt(c.reported_remaining_minor) !== accountRemaining ||
        BigInt(c.root_attributed_minor) !== amount ||
        BigInt(c.reported_remaining_minor) +
          BigInt(c.withdrawn_without_selected_transfer_minor) !==
          amount
      )
        throw Error("Cross-account claim conservation failed.")
    }
    if (
      result.hops.length !== pairs.length ||
      new Set(result.hops.map((h) => h.debit_id)).size !== pairs.length
    )
      throw Error("Transfer hops differ.")
    for (const h of result.hops) {
      const d = scope.rows.find((r) => r.key === h.debit_id),
        c = scope.rows.find((r) => r.key === h.credit_id)
      if (
        !d ||
        !c ||
        h.backward_timing !== backward(h.debit_id, h.credit_id) ||
        (expectedBackward &&
          value.calculation_account_order.indexOf(h.from_account) >=
            value.calculation_account_order.indexOf(h.to_account)) ||
        !pairs.some(
          (p) => p.debit_id === h.debit_id && p.credit_id === h.credit_id
        ) ||
        d.currency !== currency ||
        c.currency !== currency ||
        d.amount_minor !== h.amount_minor ||
        c.amount_minor !== h.amount_minor ||
        d.direction !== "debit" ||
        c.direction !== "credit" ||
        !scope.candidates.some(
          (p) => p.debit_id === h.debit_id && p.credit_id === h.credit_id
        ) ||
        Object.keys(h.propagated_by_claim).some((claim) => !roots.has(claim)) ||
        d.account_id !== h.from_account ||
        c.account_id !== h.to_account ||
        Object.values(h.propagated_by_claim).reduce(
          (n, a) => n + BigInt(a),
          0n
        ) +
          BigInt(h.unattributed_or_unidentified_minor) !==
          BigInt(h.amount_minor)
      )
        throw Error("Transfer hop differs from its sources.")
    }
    for (const account of Object.values(result.accounts)) {
      if (
        account.currency !== currency ||
        [
          account.closing_balance,
          account.lowest_balance,
          ...Object.values(account.outcomes).flatMap((o) => [
            o.deposited,
            o.surviving,
            o.withdrawn,
          ]),
        ].some((m) => m.currency !== currency)
      )
        throw Error("Tracing currency differs.")
      for (const o of Object.values(account.outcomes))
        if (
          BigInt(o.deposited.minor_units) !==
          BigInt(o.surviving.minor_units) + BigInt(o.withdrawn.minor_units)
        )
          throw Error("Account claim totals do not reconcile.")
    }
  }
  return { envelope, value }
}
