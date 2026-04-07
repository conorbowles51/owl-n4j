import type { EvidenceFileRecord } from "@/types/evidence.types"

export type DisplayProcessingStatus =
  | "unprocessed"
  | "processing"
  | "processed"
  | "failed"
  | "stale"

export function getDisplayStatus(file: Pick<EvidenceFileRecord, "status" | "processing_stale">): DisplayProcessingStatus {
  if (file.processing_stale && file.status === "processed") {
    return "stale"
  }
  return file.status
}
