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

export type PrivilegeMarking = "unmarked" | "confidential" | "privileged_confidential"

export const PRIVILEGE_MARKING_LABELS: Record<PrivilegeMarking, string> = {
  unmarked: "No privilege marking",
  confidential: "Confidential",
  privileged_confidential: "Privileged and confidential",
}

export const snapshotsAPI = {
  create: (snapshot: SnapshotCreateData) =>
    fetchAPI<Snapshot>("/api/snapshots", {
      method: "POST",
      body: snapshot,
    }),

  list: (caseId?: string) =>
    fetchAPI<Snapshot[]>(caseId ? `/api/snapshots?case_id=${encodeURIComponent(caseId)}` : "/api/snapshots"),

  get: (snapshotId: string) =>
    fetchAPI<Snapshot>(`/api/snapshots/${snapshotId}`),

  /** The snapshot report PDF: its graph, its own events with their sources, and the chosen privilege marking. */
  report: async (snapshotId: string, privilegeMarking: PrivilegeMarking): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch(`/api/snapshots/${encodeURIComponent(snapshotId)}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ privilege_marking: privilegeMarking }),
    })
    if (!response.ok) {
      const detail = await response.json().then((b) => b?.detail).catch(() => null)
      throw new Error(typeof detail === "string" ? detail : `Report not produced (${response.status})`)
    }
    const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")
    return { blob: await response.blob(), filename: match?.[1] ?? "snapshot-report.pdf" }
  },

  delete: (snapshotId: string) =>
    fetchAPI<void>(`/api/snapshots/${snapshotId}`, { method: "DELETE" }),
}
