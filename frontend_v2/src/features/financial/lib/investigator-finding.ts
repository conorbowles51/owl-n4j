import type {
  CaseworkEntry,
  CaseworkLinkInput,
} from "@/features/workspace/casework-api"
import { readSelectedPayments } from "./selected-payment-source"

// Stored kind keys are retained for existing casework: the former observation
// action is Create Finding; the former question action is Create Observation.
export const findingKindLabel = (kind: string) =>
  kind === "question" ? "Observation" : "Finding"

export type FindingKind = "question" | "observation" | "conclusion"
export interface InvestigatorFindingDraft {
  title: string
  explanation: string
  nextAction: string
  owner: string
  kind: FindingKind
  progress: "open" | "in-progress" | "complete"
}
export const emptyFinding: InvestigatorFindingDraft = {
  title: "",
  explanation: "",
  nextAction: "",
  owner: "",
  kind: "observation",
  progress: "open",
}
const escape = (text: string) => text.replace(/^(\\*## )/gm, "\\$1")
const unescape = (text: string) => text.replace(/^\\(\\*## )/gm, "$1")

export function findingBody(draft: InvestigatorFindingDraft) {
  return `${escape(draft.explanation)}\n\n## Next action\n${escape(draft.nextAction)}\n\n## Assigned to\n${escape(draft.owner)}`
}
export function findingDraft(entry: CaseworkEntry): InvestigatorFindingDraft {
  const match = entry.tags.includes("financial-workspace")
    ? // Saved text can have its final newline trimmed when Assigned to is empty.
      // Read those existing records without showing storage headings or changing them.
      /^(.*)\n\n## Next action\n(.*)\n\n## Assigned to(?:\n(.*))?$/s.exec(
        entry.body.replace(/\r\n/g, "\n")
      )
    : null
  return {
    title: entry.title || "",
    explanation: match ? unescape(match[1]) : entry.body,
    nextAction: match ? unescape(match[2]) : "",
    owner: match ? unescape(match[3] ?? "") : "",
    kind: entry.tags.includes("financial-conclusion")
      ? "conclusion"
      : entry.tags.includes("financial-observation")
        ? "observation"
        : "question",
    progress: entry.tags.includes("financial-complete")
      ? "complete"
      : entry.tags.includes("financial-in-progress")
        ? "in-progress"
        : "open",
  }
}
export function findingTags(
  draft: InvestigatorFindingDraft,
  previous: string[] = []
) {
  return [
    ...new Set([
      ...previous.filter(
        (tag) =>
          !/^financial-(?:entry-(?:finding|observation)|(?:question|observation|conclusion)(?:-(?:open|in-progress|complete))?|open|in-progress|complete)$/.test(
            tag
          )
      ),
      "financial",
      "financial-workspace",
      `financial-entry-${draft.kind === "question" ? "observation" : "finding"}`,
      `financial-${draft.kind}`,
      `financial-${draft.progress}`,
      `financial-${draft.kind}-${draft.progress}`,
    ]),
  ]
}
export function findingPaymentIds(entry: CaseworkEntry) {
  return [
    ...new Set(
      entry.links.flatMap((link) =>
        Array.isArray(link.source_anchor?.financial_transaction_ids)
          ? link.source_anchor.financial_transaction_ids.filter(
              (id): id is string => typeof id === "string"
            )
          : []
      )
    ),
  ]
}

export async function captureFindingPayments(
  caseId: string,
  ids: string[],
  signal?: AbortSignal
): Promise<CaseworkLinkInput[]> {
  const links = new Map<string, CaseworkLinkInput>()
  for (let offset = 0; offset < ids.length; offset += 500) {
    const sources = await readSelectedPayments(
      caseId,
      ids.slice(offset, offset + 500),
      signal
    )
    for (const source of sources) {
      if (
        source.ledger_status !== "admitted" ||
        source.superseded_by_id !== null
      )
        throw Error(
          "A selected payment has changed or was excluded. Open its details and update the selection before saving."
        )
      const link = links.get(source.evidence_file_id) ?? {
        target_type: "evidence",
        target_id: source.evidence_file_id,
        target_label: source.filename,
        relationship: "context",
        source_anchor: { financial_transaction_ids: [], financial_ref_ids: [] },
        metadata: {
          schema: "loupe.financial.payment_selection/1",
          transactions: [],
        },
      }
      ;(link.source_anchor!.financial_transaction_ids as string[]).push(
        source.transaction_id
      )
      ;(link.source_anchor!.financial_ref_ids as string[]).push(source.ref_id)
      ;(link.metadata!.transactions as unknown[]).push(source.transaction)
      links.set(source.evidence_file_id, link)
    }
  }
  const result = [...links.values()]
  if (
    new TextEncoder().encode(JSON.stringify(result)).length >
    32 * 1024 * 1024
  )
    throw Error(
      "These payment details exceed 32 MB. Save a smaller selection; your draft is retained."
    )
  return result
}
