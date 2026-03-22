import { fetchAPI } from "@/lib/api-client"
import type { EvidenceJob } from "@/types/evidence.types"

export const jobsAPI = {
  list: async (caseId: string) => {
    const res = await fetchAPI<EvidenceJob[]>(
      `/api/evidence-folders/jobs?case_id=${caseId}`
    )
    // Fallback: try evidence engine jobs endpoint
    return res
  },

  listFromEngine: async (caseId: string) => {
    // Get jobs directly from evidence engine via backend proxy
    const res = await fetchAPI<EvidenceJob[]>(
      `/api/evidence/engine/jobs?case_id=${caseId}`
    )
    return res
  },

  getStatus: (jobId: string) =>
    fetchAPI<EvidenceJob>(`/api/evidence/engine/jobs/${jobId}`),
}
