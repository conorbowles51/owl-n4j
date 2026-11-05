import type { CollectLink } from "@/features/phones/collect.api"
import type { SearchHit } from "../api"

/** Add to… on a search hit (07 J-5, 6.1): the saved link of what the hit stands for, or null when nothing can be saved. */
export function hitLink(hit: SearchHit, q: string): CollectLink | null {
  const label = hit.title
  const anchor = { origin: "search", query: q, ...(hit.page ? { page: hit.page } : {}) }
  const extraction = (hit.open.params as Record<string, unknown>).phone ?? (hit.open.params as Record<string, unknown>).extraction_id
  if (hit.record_uid) {
    return { target_type: "phone_record", target_id: hit.record_uid, label, source_anchor: { ...anchor, ...(extraction ? { extraction_id: extraction } : {}) } }
  }
  if (hit.file_uid) return { target_type: "phone_file", target_id: hit.file_uid, label, source_anchor: anchor }
  if (hit.identity_key) return { target_type: "phone_identity", target_id: hit.identity_key, label, source_anchor: anchor }
  if (hit.evidence_file_id) return { target_type: "evidence", target_id: hit.evidence_file_id, label, source_anchor: anchor }
  if (hit.transaction_id) return { target_type: "financial_transaction", target_id: hit.transaction_id, label, source_anchor: anchor }
  return null
}

/** The groups kept as one phone selection when they run past 500, as a whole filtered result is (07 6.1). */
export const SELECTION_GROUPS = new Set(["messages", "calls", "emails", "records", "machine_text"])
export const SELECTION_AS_ONE = 500

/** What a target kind cannot take for this group (07 6.1: an identity reaches a dossier only through a link decision). */
export function dossierRefused(group: string): string | null {
  if (group === "people") return "A person's numbers and accounts join a dossier through a link decision in Phone identities, so dossiers are not offered here."
  if (group === "payments") return "Payments are collected into findings, theories and notes, so dossiers are not offered here."
  return null
}

export function noun(group: string): string {
  return ({ messages: "messages", calls: "calls", emails: "emails", people: "identifiers", records: "records", documents: "documents", machine_text: "records", payments: "payments" } as Record<string, string>)[group] ?? "hits"
}
