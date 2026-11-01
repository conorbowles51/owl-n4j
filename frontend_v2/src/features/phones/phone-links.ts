import { isPhoneLinkType, type PhoneLinkType } from "@/generated/link-types"

/**
 * How a phone link opens and reads in Workspace, Notebook and dossier views (07 section 6.4 item 11).
 * Routes follow 07 section 4.13; the phone screens read the query parameter that names the item.
 */
export interface PhoneLinkLike {
  target_type: string
  target_id: string
  target_label?: string | null
  label?: string | null
  source_anchor?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
}

export { isPhoneLinkType }

const text = (value: unknown) => (typeof value === "string" && value.trim() ? value.trim() : undefined)

function field(link: PhoneLinkLike, name: string) {
  return text(link.source_anchor?.[name]) ?? text(link.metadata?.[name])
}

export function phoneLinkHref(caseId: string, link: PhoneLinkLike): string | null {
  if (!isPhoneLinkType(link.target_type)) return null
  const base = `/cases/${encodeURIComponent(caseId)}`
  const id = encodeURIComponent(link.target_id)
  const extraction = field(link, "extraction_id")
  const recordType = field(link, "record_type")
  const type = link.target_type as PhoneLinkType
  switch (type) {
    case "phone_extraction":
      return `${base}/phones/${id}`
    case "phone_record":
      return extraction && recordType
        ? `${base}/phones/${encodeURIComponent(extraction)}/records/${encodeURIComponent(recordType)}?record=${id}`
        : `${base}/phones?record=${id}`
    case "phone_thread":
      return extraction
        ? `${base}/phones/${encodeURIComponent(extraction)}/records/conversations?thread=${id}`
        : `${base}/phones?thread=${id}`
    case "phone_analysis":
      return `${base}/phone-analyses/${encodeURIComponent(field(link, "kind") ?? "results")}?snapshot=${id}`
    case "statement_check":
      return `${base}/phone-analyses/statement-check?check=${id}`
    case "phone_identity":
      return `${base}/phones?identity=${id}`
    case "phone_file":
      return `${base}/phones?file=${id}`
    case "phone_selection":
      return `${base}/phones?selection=${id}`
    case "phone_view":
      return `${base}/phones?view=${id}`
  }
}

/** The recorded time in its own zone, e.g. "2024-03-01 23:30 (America/New_York)". */
export function phoneTimeWithZone(link: PhoneLinkLike): string | undefined {
  const instant = field(link, "instant")
  if (!instant) return undefined
  const match = instant.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/)
  if (!match) return undefined
  const offset = instant.match(/(Z|[+-]\d{2}:?\d{2})$/)?.[1]
  const zone = field(link, "zone") ?? (offset === "Z" ? "UTC" : offset)
  return zone ? `${match[1]} ${match[2]} (${zone})` : `${match[1]} ${match[2]} (zone not recorded)`
}

const NAMES: Record<PhoneLinkType, string> = {
  phone_record: "Phone record",
  phone_file: "Phone file",
  phone_thread: "Conversation",
  phone_identity: "Phone identity",
  phone_extraction: "Phone",
  phone_analysis: "Phone analysis",
  phone_selection: "Phone selection",
  phone_view: "Saved phone view",
  statement_check: "Statement check",
}

export interface PhoneLinkSummary {
  label: string
  kind: string
  app?: string
  time?: string
  badges: string[]
}

export function phoneLinkSummary(link: PhoneLinkLike): PhoneLinkSummary {
  const type = link.target_type as PhoneLinkType
  const badges = [
    ...(Array.isArray(link.metadata?.badges) ? link.metadata!.badges : []),
    ...(Array.isArray(link.source_anchor?.badges) ? link.source_anchor!.badges : []),
  ].filter((value): value is string => typeof value === "string" && !!value.trim())
  const count = link.metadata?.record_count ?? link.source_anchor?.record_count
  if (type === "phone_selection" && typeof count === "number") badges.push(`${count.toLocaleString()} records`)
  return {
    label: link.target_label || link.label || NAMES[type] || "Phone item",
    kind: NAMES[type] ?? "Phone item",
    app: field(link, "app"),
    time: phoneTimeWithZone(link),
    badges: Array.from(new Set(badges)),
  }
}

/**
 * Significant holds graph keys only (07 6.1, 6.4 item 12): it is offered on graph nodes, including the phone
 * nodes (PhoneExtraction, PhoneIdentity, PhoneGroup), and never on phone records, files, threads, selections or
 * results, which are not graph keys.
 */
export function significantOfferedForLink(targetType: string): boolean {
  return targetType === "graph_entity" || targetType === "phone_identity" || targetType === "phone_extraction"
}

/** A graph node of the phone build's identity type; "Add to Dossiers" goes through the identity decision. */
export function isPhoneIdentityNode(nodeType: string | undefined): boolean {
  return nodeType === "PhoneIdentity"
}

/** Where "Add to Dossiers" on a phone identity goes: the identity decision (link_phone_identity), never a new
 * dossier keyed on the graph node. */
export function phoneIdentityDecisionHref(caseId: string, identityKey: string): string {
  return `/cases/${encodeURIComponent(caseId)}/phone-review?decision=link_phone_identity&identity=${encodeURIComponent(identityKey)}`
}
