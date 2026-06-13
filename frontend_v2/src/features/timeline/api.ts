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

/** Color palette for event types — light mode */
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

/** Color palette for event types — dark mode (one Tailwind shade lighter) */
const EVENT_TYPE_COLORS_DARK: Record<string, string> = {
  Transaction: "#FCD34D",
  Transfer: "#FDBA74",
  Payment: "#FCA5A5",
  Communication: "#67E8F9",
  Email: "#93C5FD",
  PhoneCall: "#C4B5FD",
  Meeting: "#F9A8D4",
  Travel: "#5EEAD4",
  Filing: "#94A3B8",
  Registration: "#BEF264",
  Incorporation: "#D8B4FE",
  Seizure: "#FCA5A5",
}

const EVENT_TYPE_FALLBACK_PALETTE = [
  "#6366F1", "#10B981", "#F43F5E", "#0EA5E9",
  "#D946EF", "#FBBF24", "#34D399", "#FB7185",
]

const EVENT_TYPE_FALLBACK_PALETTE_DARK = [
  "#A5B4FC", "#6EE7B7", "#FDA4AF", "#7DD3FC",
  "#F0ABFC", "#FDE68A", "#6EE7B7", "#FDB7C0",
]

export function getEventTypeColor(type: string, isDark?: boolean): string {
  const palette = isDark ? EVENT_TYPE_COLORS_DARK : EVENT_TYPE_COLORS
  const fallback = isDark ? EVENT_TYPE_FALLBACK_PALETTE_DARK : EVENT_TYPE_FALLBACK_PALETTE
  if (palette[type]) return palette[type]
  // Hash-based consistent fallback
  let hash = 0
  for (let i = 0; i < type.length; i++) {
    hash = type.charCodeAt(i) + ((hash << 5) - hash)
  }
  return fallback[Math.abs(hash) % fallback.length]
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
