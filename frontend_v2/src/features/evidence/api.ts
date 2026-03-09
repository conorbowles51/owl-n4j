import { fetchAPI } from "@/lib/api-client"
import type { EvidenceFile } from "@/types/evidence.types"

export const evidenceAPI = {
  list: (caseId: string, status?: string) => {
    const qs = new URLSearchParams({ case_id: caseId })
    if (status) qs.set("status", status)
    return fetchAPI<EvidenceFile[]>(`/api/evidence?${qs}`)
  },

  upload: (caseId: string, files: File[]) => {
    const formData = new FormData()
    formData.append("case_id", caseId)
    files.forEach((f) => formData.append("files", f))
    return fetchAPI<{ uploaded: number }>("/api/evidence/upload", {
      method: "POST",
      body: formData,
    })
  },

  process: (
    caseId: string,
    fileIds: string[],
    profile?: string
  ) =>
    fetchAPI<void>("/api/evidence/process", {
      method: "POST",
      body: { case_id: caseId, file_ids: fileIds, profile },
    }),

  delete: (
    evidenceId: string,
    caseId: string,
    deleteExclusiveEntities = false
  ) =>
    fetchAPI<void>(
      `/api/evidence/${evidenceId}?case_id=${caseId}&delete_exclusive_entities=${deleteExclusiveEntities}`,
      { method: "DELETE" }
    ),

  logs: (caseId: string, limit = 50) =>
    fetchAPI<unknown[]>(`/api/evidence/logs?case_id=${caseId}&limit=${limit}`),
}
