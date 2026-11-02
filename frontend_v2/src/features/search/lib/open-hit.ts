import { recordPath } from "@/lib/record-links"
import type { SearchHit } from "../api"

/** Where a search hit opens (03 section 11.2): messages in their whole thread with the record beside it, people
 * in Conversations' people tab, other records in the record panel, documents in the viewer at the page. */
export function hitPath(caseId: string, hit: SearchHit): string {
  const c = `/cases/${encodeURIComponent(caseId)}`
  const p = hit.open.params as Record<string, string | number | null | undefined>
  const enc = (v: unknown) => encodeURIComponent(String(v))
  switch (hit.open.screen) {
    case "conversations": {
      // the whole unfiltered thread at that message, the search's matches marked (S-8)
      const q = new URLSearchParams()
      if (p.thread) q.set("thread", String(p.thread))
      else q.set("record", String(hit.record_uid))
      if (p.event) q.set("at", String(p.event))
      if (p.q) q.set("hl", String(p.q))
      if (p.exact) q.set("hlexact", "1")
      return `${c}/phones/${enc(p.phone)}/records/conversations?${q}`
    }
    case "people":
      return `${c}/conversations?tab=people&people=${enc(p.people)}`
    case "dossier":
      return `${c}/dossiers?dossier=${enc(p.id)}`
    case "record":
      return recordPath(caseId, String(p.record_uid))
    case "document":
      return `${c}/evidence?file=${enc(p.evidence_file_id)}${p.page ? `&page=${enc(p.page)}` : ""}`
    default:
      return c
  }
}

/** Conversations with the text filter: the full list behind a group's total (S-4). */
export function conversationsWithText(caseId: string, q: string, kinds: string[], exact: boolean): string {
  const p = new URLSearchParams({ q })
  if (kinds.length) p.set("kinds", kinds.join(","))
  if (exact) p.set("exact", "1")
  return `/cases/${encodeURIComponent(caseId)}/conversations?${p}`
}
