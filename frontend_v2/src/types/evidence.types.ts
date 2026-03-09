export interface EvidenceFile {
  id: string
  filename: string
  file_type: string
  file_size: number
  status: "processed" | "processing" | "queued" | "failed" | "unprocessed"
  uploaded_at: string
  processed_at?: string
  entity_count?: number
  error_message?: string
}

export interface IngestionResult {
  file_id: string
  status: string
  entities_extracted: number
  relationships_extracted: number
  processing_time_ms: number
}
