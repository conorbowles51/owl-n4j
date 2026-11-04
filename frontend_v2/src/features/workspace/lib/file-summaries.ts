import type { EvidenceFile } from "@/types/evidence.types"

export function filesWithSummaries(files: EvidenceFile[]) {
  const summarised = files
    .filter((f) => typeof f.summary === "string" && f.summary.trim() !== "")
    .sort((a, b) => String(b.processed_at ?? b.created_at).localeCompare(String(a.processed_at ?? a.created_at)))
  return { summarised, total: files.length }
}
