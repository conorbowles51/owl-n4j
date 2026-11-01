import type { Origin, RowBadge } from "./ui/OriginMark"

export interface PartyView {
  key?: string
  /** The name this phone saved, or null when none. */
  name: string | null
  /** The number or account, or null when the report has none (the phone's owner without a number). */
  identifier: string | null
  isOwner?: boolean
}

/** What the record panel and rows show for one phone record (message, call or any record type). */
export interface PhoneRecordView {
  id: string
  kind: "message" | "call" | "record"
  typeWords: string
  phone: { id: string; label: string; index: number; extractionDate?: string }
  app?: string
  /** ISO instant, or null when the record has no time. */
  time: string | null
  zone: string
  direction?: "incoming" | "outgoing" | null
  from?: PartyView
  to?: PartyView[]
  body?: string | null
  origin: Origin
  badges: RowBadge[]
  usedIn?: { findings: number; dossiers: number; notes: number; timeline: number; labels: number }
  /** For other record types: field label and value pairs, from the record's own fields. */
  fields?: { label: string; value: string }[]
}

/** "Name (number)", or the parts that exist; the owner without a number reads "This phone's owner (no number)". */
export function partyWords(p: PartyView | undefined): string {
  if (!p) return "Unknown"
  if (p.isOwner && !p.identifier) return p.name ? `${p.name} (no number in the report)` : "This phone's owner (no number in the report)"
  if (p.name && p.identifier) return `${p.name} (${p.identifier})`
  return p.name ?? p.identifier ?? "Unknown"
}

/** "Name (number) → Name (number)", the form used on every mixed-stream row, in copy and in export (07 4.4). */
export function participantsLine(r: Pick<PhoneRecordView, "from" | "to">): string {
  const to = (r.to ?? []).map(partyWords).join(", ")
  return `${partyWords(r.from)} → ${to || "Unknown"}`
}
