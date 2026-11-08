/** Words for Deleted items (components/DeletedEvidenceDialog.tsx). */

export function size(bytes: number) {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} bytes`
}

const COUNT_WORDS: [string, string][] = [
  ["rows_removed", "records"],
  ["folders_removed", "folders"],
  ["files_removed", "files removed from disk"],
  ["files_kept_shared", "files kept because another item still uses them"],
  ["files_kept_production", "phone production files kept"],
  ["graph_documents_removed", "graph documents"],
  ["graph_entities_removed", "graph entities"],
]

/** What a removal for good took, in words, for the person who asked for it. */
export function purgeSummary(label: string | null, counts: Record<string, number>) {
  const parts = COUNT_WORDS.filter(([key]) => (counts[key] ?? 0) > 0).map(
    ([key, words]) => `${counts[key].toLocaleString()} ${words}`
  )
  const freed = counts.bytes_on_disk_freed ? `, ${size(counts.bytes_on_disk_freed)} freed` : ""
  return `Removed ${label ?? "the item"} for good: ${parts.length ? parts.join(", ") : "nothing else was left"}${freed}`
}
