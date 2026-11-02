import type { StreamRow } from "../schemas"

/**
 * Record state badges (03 section 3.5): words in priority order, the captured value on hover; every file outcome of
 * 01 section 7.2 other than a match has its badge.
 */

export const FILE_OUTCOME_BADGE: Record<string, string | null> = {
  missing: "File missing from production",
  no_local_path: "No file path in report",
  empty_placeholder: "Empty placeholder in production",
  size_mismatch: "File size differs from report",
  mismatch: "File does not match its hash",
  no_hash: "File not checked",
  match: null,
}

const PRIORITY = [
  "Corrected",
  "Mapped by the system, not yet confirmed",
  "Deleted",
  "In trash",
  "Recovered by carving",
  "May come from another device",
  "Found",
]

export interface Badge {
  words: string
  hover?: string
  tone: "review" | "deleted" | "plain"
}

function tone(words: string): Badge["tone"] {
  if (words.startsWith("Corrected") || words.startsWith("Mapped by the system") || words.startsWith("Machine-generated")) return "review"
  if (["Deleted", "In trash", "Recovered by carving"].includes(words) || words.startsWith("File")) return "deleted"
  return "plain"
}

function rank(words: string): number {
  const i = PRIORITY.findIndex((p) => words.startsWith(p))
  return i < 0 ? PRIORITY.length : i
}

export function rowBadges(row: StreamRow): Badge[] {
  const out: Badge[] = []
  for (const f of row.flags) {
    if (f === "No time recorded") continue // the time cell says it
    out.push({ words: f, hover: f === "Deleted" || f === "In trash" || f === "Deletion state unknown" ? `deleted_state as captured` : undefined, tone: tone(f) })
  }
  if (row.copies.count > 1) out.push({ words: `Found ${row.copies.count} times`, hover: row.copies.apps.filter(Boolean).join(", "), tone: "plain" })
  const outcomes = new Set(row.attachments.map((a) => a.verification).filter((v): v is string => !!v))
  for (const v of outcomes) {
    const w = FILE_OUTCOME_BADGE[v]
    if (w) out.push({ words: w, hover: `verification: ${v}`, tone: "deleted" })
  }
  if (row.owner_read.date_read) out.push({ words: "Read by owner", tone: "plain" })
  if (row.owner_read.date_played) out.push({ words: "Played by owner", tone: "plain" })
  return out.sort((a, b) => rank(a.words) - rank(b.words))
}
