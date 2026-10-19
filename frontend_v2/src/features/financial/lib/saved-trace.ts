import { z } from "zod"
import type { CaseworkLinkInput } from "@/features/workspace/casework-api"
import { traceScenarioSchema } from "./ledger-trace"
import { networkTraceScenarioSchema } from "./network-trace"
import { renderTraceReport, type VerifiedTrace } from "./trace-report"

const envelopeSchema = z.object({
  case_id: z.string(),
  account_id: z.string().optional(),
  applied: z.literal(false),
  scenario_json: z.string().max(16 * 1024 * 1024),
  scenario_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  scenario_byte_count: z
    .number()
    .int()
    .positive()
    .max(16 * 1024 * 1024),
})
export async function readSavedTrace(
  raw: unknown,
  caseId: string
): Promise<VerifiedTrace> {
  const envelope = envelopeSchema.parse(raw)
  if (envelope.case_id !== caseId)
    throw Error("This calculation belongs to another case.")
  const captured = JSON.parse(envelope.scenario_json)
  if (captured.case_id !== caseId)
    throw Error("The saved calculation does not match this case.")
  const value =
    captured.schema === "loupe.financial.conditional_trace/1"
      ? traceScenarioSchema.parse(captured)
      : networkTraceScenarioSchema.parse(captured)
  if ("account_id" in value && envelope.account_id !== value.account_id)
    throw Error("The saved account does not match the calculation.")
  const trace = { envelope, value } as VerifiedTrace
  // Uses the report's existing checks for the exact bytes, case and captured source ledger.
  await renderTraceReport(trace)
  return trace
}
export async function traceFindingLinks(
  trace: VerifiedTrace
): Promise<CaseworkLinkInput[]> {
  await readSavedTrace(trace.envelope, trace.envelope.case_id)
  const captured = JSON.parse(trace.envelope.scenario_json)
  const sources = z
    .array(
      z.object({
        row: z.object({
          key: z.string(),
          ref_id: z.string().nullable().optional(),
        }),
        source: z.object({ evidence_file_id: z.string().uuid().nullable() }),
      })
    )
    .max(25000)
    .parse(captured.ledger_snapshot.ledger.readings)
  const included = new Set(
    z.array(z.string()).parse(captured.inputs.ordered_transaction_ids)
  )
  const links = new Map<string, CaseworkLinkInput>()
  for (const { row, source } of sources) {
    if (!source.evidence_file_id || !included.has(row.key)) continue
    const link = links.get(source.evidence_file_id) ?? {
      target_type: "evidence",
      target_id: source.evidence_file_id,
      relationship: "context",
      source_anchor: { financial_transaction_ids: [], financial_ref_ids: [] },
      metadata: { trace_sha256: trace.envelope.scenario_sha256 },
    }
    const ids = link.source_anchor!.financial_transaction_ids as string[]
    if (!ids.includes(row.key)) ids.push(row.key)
    const refs = link.source_anchor!.financial_ref_ids as string[]
    if (row.ref_id && !refs.includes(row.ref_id)) refs.push(row.ref_id)
    links.set(source.evidence_file_id, link)
  }
  if (!links.size)
    throw Error(
      "This calculation has no linked source files. Download the report to retain it."
    )
  const result = [...links.values()]
  result[0].metadata = {
    ...result[0].metadata,
    schema: "loupe.financial.saved_trace/1",
    envelope: trace.envelope,
  }
  return result
}
