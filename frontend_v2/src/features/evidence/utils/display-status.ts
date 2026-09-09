import type { EvidenceFileRecord } from "@/types/evidence.types"

export type DisplayProcessingStatus =
  | "unprocessed"
  | "processing"
  | "processed"
  | "failed"

export function getDisplayStatus(file: Pick<EvidenceFileRecord, "status">): DisplayProcessingStatus {
  return file.status
}
