import { fetchAPI } from "@/lib/api-client"

export interface TimelineConnection {
  key: string
  name: string
  type: string
  relationship: string
  direction: "incoming" | "outgoing"
}

export interface TimelineEvent {
  key: string
  name: string
  type: string
  date: string
  time: string | null
  amount: string | null
  summary: string | null
  notes: string | null
  connections: TimelineConnection[]
}

/** Color palette for event types — visually distinct, works on both light/dark */
export const EVENT_TYPE_COLORS: Record<string, string> = {
  Transaction: "#F59E0B",
  Transfer: "#F97316",
  Payment: "#EF4444",
  Communication: "#06B6D4",
  Email: "#3B82F6",
  PhoneCall: "#8B5CF6",
  Meeting: "#EC4899",
  Travel: "#14B8A6",
  Filing: "#64748B",
  Registration: "#84CC16",
  Incorporation: "#A855F7",
  Seizure: "#DC2626",
}

const EVENT_TYPE_FALLBACK_PALETTE = [
  "#6366F1", "#10B981", "#F43F5E", "#0EA5E9",
  "#D946EF", "#FBBF24", "#34D399", "#FB7185",
]

export function getEventTypeColor(type: string): string {
  if (EVENT_TYPE_COLORS[type]) return EVENT_TYPE_COLORS[type]
  // Hash-based consistent fallback
  let hash = 0
  for (let i = 0; i < type.length; i++) {
    hash = type.charCodeAt(i) + ((hash << 5) - hash)
  }
  return EVENT_TYPE_FALLBACK_PALETTE[Math.abs(hash) % EVENT_TYPE_FALLBACK_PALETTE.length]
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

  getEventTypes: async () => {
    const data = await fetchAPI<{ event_types: string[] }>("/api/timeline/types")
    return data.event_types
  },
}
