import type { Lead } from "./api"

/** What a Corroborate question can hold (backend case_selections GROUP_MEMBER_TYPES["relation_query"]). */
const ASKABLE = new Set(["graph_entity", "financial_transaction", "financial_account", "financial_party", "evidence", "timeline_event",
  "phone_record", "entry", "place", "person", "phone", "document_row", "claim"])

/** The lead's records a question can hold, and the rest counted by kind so the page names them (a lead can cite dated
 * document lines, which a question cannot hold: one in the set made the server refuse the whole question). */
export function leadMembers(lead: Lead): { members: { type: string; id: string }[]; skipped: { type: string; count: number }[] } {
  const members: { type: string; id: string }[] = []
  const skipped = new Map<string, number>()
  for (const r of lead.record_refs.slice(0, 2000)) {
    const i = r.indexOf(":")
    const type = r.slice(0, i)
    if (ASKABLE.has(type)) members.push({ type, id: r.slice(i + 1) })
    else skipped.set(type, (skipped.get(type) ?? 0) + 1)
  }
  return { members, skipped: [...skipped].map(([type, count]) => ({ type, count })) }
}
