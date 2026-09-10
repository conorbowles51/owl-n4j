import { z } from "zod"
import type {
  CaseworkCreateInput,
  CaseworkLinkInput,
} from "@/features/workspace/casework-api"
import type { VerifiedClaimComparison } from "./claim-comparison"
export function claimReviewNote(
  report: VerifiedClaimComparison,
  decision: "agree" | "disagree",
  reason: string,
  readingIds: string[]
): CaseworkCreateInput {
  if (!reason.trim()) throw Error("Explain your response to the proposal.")
  if (
    readingIds.length > 20 ||
    new Set(readingIds).size !== readingIds.length ||
    readingIds.some(
      (id) =>
        !report.value.comparison.candidates.some(
          (c) => c.entry.transaction_id === id
        )
    )
  )
    throw Error("Choose at most20 distinct compared readings.")
  const captured = z
    .object({
      ledger_snapshot: z.object({
        ledger: z.object({
          readings: z.array(
            z.object({
              row: z.object({ key: z.string() }).passthrough(),
              source: z
                .object({ evidence_file_id: z.string().uuid().nullable() })
                .passthrough(),
              provenance: z.unknown(),
            })
          ),
        }),
      }),
    })
    .parse(JSON.parse(report.envelope.scenario_json))
  const supporting = captured.ledger_snapshot.ledger.readings.filter((r) =>
    readingIds.includes(r.row.key)
  )
  if (
    supporting.length !== readingIds.length ||
    supporting.some((r) => !r.source.evidence_file_id)
  )
    throw Error("Selected readings do not have complete evidence references.")
  const metadata = {
    schema: "loupe.financial.claim_review/1",
    decision,
    proposal: report.value.comparison.outcome,
    comparison_sha256: report.envelope.scenario_sha256,
    snapshot_sha256: report.value.snapshot_sha256,
    claim_proof_class: "p4",
    inputs: report.value.inputs,
    limitations: report.value.limitations,
    comparison_notes: report.value.comparison.notes,
    selected_candidates: report.value.comparison.candidates.filter((c) =>
      readingIds.includes(c.entry.transaction_id)
    ),
  }
  const links = new Map<string, CaseworkLinkInput>()
  links.set(report.value.claim_source.id, {
    target_type: "evidence",
    target_id: report.value.claim_source.id,
    target_label: report.value.claim_source.filename,
    relationship: "context",
    source_anchor: {
      quote: report.value.inputs.quote,
      location: report.value.inputs.source_location,
    },
    metadata: {
      ...metadata,
      claim_source: report.value.claim_source,
      sources: [],
    },
  })
  for (const r of supporting) {
    const id = r.source.evidence_file_id!,
      link = links.get(id) ?? {
        target_type: "evidence" as const,
        target_id: id,
        relationship: "context" as const,
        source_anchor: {},
        metadata: { ...metadata, sources: [] },
      }
    const previous = Array.isArray(link.metadata?.sources)
      ? link.metadata.sources
      : []
    link.metadata = { ...link.metadata, sources: [...previous, r] }
    link.source_anchor = {
      ...link.source_anchor,
      financial_transaction_ids: [
        ...(Array.isArray(link.source_anchor?.financial_transaction_ids)
          ? link.source_anchor.financial_transaction_ids
          : []),
        r.row.key,
      ],
    }
    links.set(id, link)
  }
  return {
    entry_type: "note",
    title: "Review of payment-claim comparison",
    body: [
      `Investigator ${decision === "agree" ? "agrees" : "disagrees"} with the rule proposal: ${report.value.comparison.outcome}.`,
      reason.trim(),
      `Original quotation: ${String(report.value.inputs.quote)}`,
      `Source: ${report.value.claim_source.filename}; ${String(report.value.inputs.source_location)}.`,
      `Claim remains P4. This review does not amend the ledger or promote evidence. Comparison reference: ${report.envelope.scenario_sha256}.`,
    ].join("\n\n"),
    tags: ["financial", "claim-comparison", `proposal-${decision}`],
    links: [...links.values()],
  }
}
