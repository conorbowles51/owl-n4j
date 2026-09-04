import type {
  CaseworkEntry,
  CaseworkEntryType,
  CaseworkLinkInput,
  LinkRelationship,
} from "./casework-api"

export const ENTRY_LABELS: Record<CaseworkEntryType, string> = {
  note: "Note",
  finding: "Finding",
  theory: "Theory",
}

export const RELATIONSHIP_LABELS: Record<LinkRelationship, string> = {
  unclassified: "Unclassified",
  supports: "Supports",
  contradicts: "Contradicts",
  context: "Context",
}

export const FINDING_STATES = ["draft", "active", "superseded", "withdrawn"]
export const THEORY_STATES = [
  "proposed",
  "investigating",
  "substantiated",
  "weakened",
  "rejected",
  "converted",
]

export function caseworkTitle(
  entry: Pick<CaseworkEntry, "entry_type" | "title" | "body">,
) {
  return (
    entry.title?.trim() ||
    entry.body.split(/\r?\n/).find(Boolean)?.replace(/^#+\s*/, "").slice(0, 90) ||
    `Untitled ${ENTRY_LABELS[entry.entry_type].toLowerCase()}`
  )
}

export function linkKey(
  link: Pick<CaseworkLinkInput, "target_type" | "target_id">,
) {
  return `${link.target_type}:${link.target_id}`
}

export function linkLabel(link: CaseworkLinkInput) {
  return link.target_label?.trim() || "Linked item"
}

export function formatCaseworkDate(value?: string | null) {
  if (!value) return "Just now"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Recently"
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function toLinkInput(link: CaseworkLinkInput): CaseworkLinkInput {
  return {
    target_type: link.target_type,
    target_id: link.target_id,
    target_label: link.target_label ?? null,
    relationship: link.relationship ?? "unclassified",
    source_anchor: link.source_anchor ?? {},
    metadata: link.metadata ?? {},
  }
}
