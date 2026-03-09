import { fetchAPI } from "@/lib/api-client"

export interface Snapshot {
  id: string
  name: string
  notes?: string
  timestamp: string
  node_count: number
  link_count: number
  timeline_count?: number
  created_at: string
  ai_overview?: string
  case_id: string
  case_version?: string
  case_name?: string
}

export interface SnapshotCreateData {
  name: string
  notes?: string
  subgraph: unknown
  timeline?: unknown
  chat_history?: unknown
  case_id: string
  [key: string]: unknown
}

export const snapshotsAPI = {
  create: (snapshot: SnapshotCreateData) =>
    fetchAPI<Snapshot>("/api/snapshots", {
      method: "POST",
      body: snapshot,
    }),

  list: () => fetchAPI<Snapshot[]>("/api/snapshots"),

  get: (snapshotId: string) =>
    fetchAPI<Snapshot>(`/api/snapshots/${snapshotId}`),

  delete: (snapshotId: string) =>
    fetchAPI<void>(`/api/snapshots/${snapshotId}`, { method: "DELETE" }),
}
