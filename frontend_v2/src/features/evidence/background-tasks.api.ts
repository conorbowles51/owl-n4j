import { fetchAPI } from "@/lib/api-client"
import type { BackgroundTask } from "@/types/evidence.types"

export const backgroundTasksAPI = {
  list: (caseId?: string, status?: string, limit = 50) => {
    const qs = new URLSearchParams()
    if (caseId) qs.set("case_id", caseId)
    if (status) qs.set("status", status)
    qs.set("limit", String(limit))
    return fetchAPI<{ tasks: BackgroundTask[] }>(`/api/background-tasks?${qs}`)
  },

  get: (taskId: string) =>
    fetchAPI<BackgroundTask>(`/api/background-tasks/${taskId}`),

  delete: (taskId: string) =>
    fetchAPI<void>(`/api/background-tasks/${taskId}`, {
      method: "DELETE",
    }),
}
