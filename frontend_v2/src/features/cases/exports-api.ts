import { fetchAPI } from "@/lib/api-client"

/** One whole-case export: a request, its progress while it is built, and the finished package. */
export interface CaseExport {
  id: string
  status: "queued" | "running" | "cancelling" | "complete" | "failed" | "cancelled" | "expired" | "removed"
  phase: string | null
  done: number
  total: number
  error: string | null
  whole: boolean
  requested_by: string
  created_at: string
  finished_at: string | null
  expires_at: string | null
  size_bytes: number | null
  sha256: string | null
  rows: number | null
  tables: number | null
  evidence_files: number | null
  graph: { nodes: number; relationships: number } | null
  vectors: Record<string, number> | null
  missing_from_disk: number | null
  differ_from_recorded_hash: number | null
  rows_private_to_others_left_out: Record<string, number> | null
}

/** The list answer also states, in the server's words, what a package holds and what it leaves out. */
export interface CaseExportList {
  exports: CaseExport[]
  holds: string
  private_note: string
  left_out: string
  kept: string
  carries_all_private: boolean
}

export const ACTIVE_EXPORT_STATUSES = ["queued", "running", "cancelling"] as const

export const caseExportsAPI = {
  list: (caseId: string) => fetchAPI<CaseExportList>(`/api/cases/${caseId}/exports`),
  request: (caseId: string) => fetchAPI<CaseExport>(`/api/cases/${caseId}/exports`, { method: "POST" }),
  cancel: (caseId: string, exportId: string) =>
    fetchAPI<CaseExport>(`/api/cases/${caseId}/exports/${exportId}/cancel`, { method: "POST" }),
  remove: (caseId: string, exportId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}/exports/${exportId}`, { method: "DELETE" }),
  /** The package is large: the browser downloads it by plain navigation, streamed, never through a blob. */
  downloadUrl: (caseId: string, exportId: string) => `/api/cases/${caseId}/exports/${exportId}/download`,
}
