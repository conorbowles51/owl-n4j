import { fetchAPI } from "@/lib/api-client"

export interface TimelineEvent {
  id: string
  type: string
  date: string
  description: string
  entity_key?: string
  entity_name?: string
  entity_type?: string
  source_file?: string
  case_id: string
}

export const timelineAPI = {
  getEvents: (params: {
    caseId: string
    types?: string[]
    startDate?: string
    endDate?: string
  }) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    if (params.types?.length) qs.set("types", params.types.join(","))
    if (params.startDate) qs.set("start_date", params.startDate)
    if (params.endDate) qs.set("end_date", params.endDate)
    return fetchAPI<{ events: TimelineEvent[]; total: number }>(
      `/api/timeline?${qs}`
    )
  },

  getEventTypes: () => fetchAPI<string[]>("/api/timeline/types"),
}
