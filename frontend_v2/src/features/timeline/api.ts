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

export interface TimelineResponse {
  events: TimelineEvent[]
  count: number
  total: number
  next_cursor?: string | null
}

export interface TimelineViewEvent {
  id: string
  view_id: string
  case_id: string
  event_key: string
  event_snapshot: Partial<TimelineEvent>
  sort_date?: string | null
  sort_time?: string | null
  position: number
  created_at?: string | null
  updated_at?: string | null
}

export interface TimelineView {
  id: string
  case_id: string
  title: string
  description?: string | null
  visibility: string
  owner_user_id?: string | null
  owner_email?: string | null
  owner_name?: string | null
  filter_snapshot: Record<string, unknown>
  export_defaults: Record<string, unknown>
  event_count: number
  created_at?: string | null
  updated_at?: string | null
  events: TimelineViewEvent[]
}

export interface TimelineViewListResponse {
  views: TimelineView[]
  total: number
}

export interface TimelineViewInput {
  case_id: string
  title: string
  description?: string | null
  event_keys?: string[]
  filter_snapshot?: Record<string, unknown>
  export_defaults?: Record<string, unknown>
}

export interface TimelineViewUpdate {
  case_id: string
  title?: string
  description?: string | null
  filter_snapshot?: Record<string, unknown>
  export_defaults?: Record<string, unknown>
}

export type TimelineViewEventAction = "add" | "remove" | "set"

export interface TimelineExportRequest {
  case_id: string
  source: "view" | "selection" | "filtered"
  format: "pdf" | "csv"
  view_id?: string | null
  event_keys?: string[]
  title?: string | null
  detail_level?: "compact" | "standard" | "detailed"
  fields?: Record<string, boolean>
  footer_label?: string
}

/** Restrained type colors for small timeline accents. */
export const EVENT_TYPE_COLORS: Record<string, string> = {
  Transaction: "#B7791F",
  Transfer: "#B45309",
  Payment: "#B91C1C",
  Communication: "#0E7490",
  Email: "#2563EB",
  PhoneCall: "#6D5BD0",
  Meeting: "#BE567C",
  Travel: "#0F766E",
  Filing: "#64748B",
  Registration: "#4D7C0F",
  Incorporation: "#7C3AED",
  Seizure: "#991B1B",
  Event: "#BE567C",
  Document: "#64748B",
  LegalAction: "#6D5BD0",
  Intelligence: "#0F766E",
  Device: "#15803D",
}

const EVENT_TYPE_FALLBACK_PALETTE = [
  "#64748B",
  "#0F766E",
  "#6D5BD0",
  "#0E7490",
  "#4D7C0F",
  "#B7791F",
  "#BE567C",
  "#475569",
]

export function getEventTypeColor(type: string): string {
  if (EVENT_TYPE_COLORS[type]) return EVENT_TYPE_COLORS[type]
  // Hash-based consistent fallback
  let hash = 0
  for (let i = 0; i < type.length; i++) {
    hash = type.charCodeAt(i) + ((hash << 5) - hash)
  }
  return EVENT_TYPE_FALLBACK_PALETTE[
    Math.abs(hash) % EVENT_TYPE_FALLBACK_PALETTE.length
  ]
}

export const timelineAPI = {
  getEvents: (params: {
    caseId: string
    types?: string[]
    startDate?: string
    endDate?: string
    limit?: number
    cursor?: string
  }) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    if (params.types?.length) qs.set("types", params.types.join(","))
    if (params.startDate) qs.set("start_date", params.startDate)
    if (params.endDate) qs.set("end_date", params.endDate)
    if (params.limit) qs.set("limit", String(params.limit))
    if (params.cursor) qs.set("cursor", params.cursor)
    return fetchAPI<TimelineResponse>(`/api/timeline?${qs}`)
  },

  getEventTypes: async () => {
    const data = await fetchAPI<{ event_types: string[] }>(
      "/api/timeline/types"
    )
    return data.event_types
  },

  listViews: (caseId: string) =>
    fetchAPI<TimelineViewListResponse>(
      `/api/timeline/views?case_id=${encodeURIComponent(caseId)}`
    ),

  getView: (caseId: string, viewId: string) =>
    fetchAPI<TimelineView>(
      `/api/timeline/views/${encodeURIComponent(viewId)}?case_id=${encodeURIComponent(caseId)}`
    ),

  createView: (input: TimelineViewInput) =>
    fetchAPI<TimelineView>("/api/timeline/views", {
      method: "POST",
      body: input,
    }),

  updateView: (viewId: string, input: TimelineViewUpdate) =>
    fetchAPI<TimelineView>(`/api/timeline/views/${encodeURIComponent(viewId)}`, {
      method: "PATCH",
      body: input,
    }),

  deleteView: (caseId: string, viewId: string) =>
    fetchAPI<void>(
      `/api/timeline/views/${encodeURIComponent(viewId)}?case_id=${encodeURIComponent(caseId)}`,
      { method: "DELETE" }
    ),

  updateViewEvents: (
    caseId: string,
    viewId: string,
    action: TimelineViewEventAction,
    eventKeys: string[]
  ) =>
    fetchAPI<TimelineView>(
      `/api/timeline/views/${encodeURIComponent(viewId)}/events:batch`,
      {
        method: "POST",
        body: {
          case_id: caseId,
          action,
          event_keys: eventKeys,
        },
      }
    ),

  downloadExport: async (request: TimelineExportRequest) => {
    const token = localStorage.getItem("authToken")
    const response = await fetch("/api/timeline/export", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      body: JSON.stringify(request),
    })
    if (!response.ok) {
      let message = `Export failed: ${response.status}`
      try {
        const data = (await response.json()) as { detail?: unknown }
        if (typeof data.detail === "string") message = data.detail
      } catch {
        // Keep status fallback.
      }
      throw new Error(message)
    }
    const blob = await response.blob()
    const disposition = response.headers.get("Content-Disposition") ?? ""
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/)?.[1]
    const quoted = disposition.match(/filename="([^"]+)"/)?.[1]
    const filename = encoded
      ? decodeURIComponent(encoded)
      : quoted || `timeline-export.${request.format}`
    return { blob, filename }
  },
}
