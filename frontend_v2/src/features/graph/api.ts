import { fetchAPI } from "@/lib/api-client"
import type { GraphData, NodeDetail } from "@/types/graph.types"

export const graphAPI = {
  getGraph: (params: {
    case_id: string
    start_date?: string
    end_date?: string
  }) => {
    const qs = new URLSearchParams({ case_id: params.case_id })
    if (params.start_date) qs.set("start_date", params.start_date)
    if (params.end_date) qs.set("end_date", params.end_date)
    return fetchAPI<GraphData>(`/api/graph?${qs}`)
  },

  getNodeDetails: (key: string, caseId: string) =>
    fetchAPI<NodeDetail>(
      `/api/graph/node/${encodeURIComponent(key)}?case_id=${caseId}`
    ),

  getNodeNeighbours: (key: string, depth: number, caseId: string) =>
    fetchAPI<GraphData>(
      `/api/graph/node/${encodeURIComponent(key)}/neighbours?depth=${depth}&case_id=${caseId}`
    ),

  search: (query: string, caseId: string, limit = 20) =>
    fetchAPI<GraphData>(
      `/api/graph/search?q=${encodeURIComponent(query)}&limit=${limit}&case_id=${caseId}`
    ),

  getSummary: (caseId: string) =>
    fetchAPI<Record<string, number>>(`/api/graph/summary?case_id=${caseId}`),

  createNode: (nodeData: Record<string, unknown>, caseId: string) =>
    fetchAPI<{ key: string }>("/api/graph/create-node", {
      method: "POST",
      body: { ...nodeData, case_id: caseId },
    }),

  updateNode: (nodeKey: string, updates: Record<string, unknown>) =>
    fetchAPI<void>(`/api/graph/node/${encodeURIComponent(nodeKey)}`, {
      method: "PUT",
      body: updates,
    }),

  deleteNode: (nodeKey: string, caseId: string, permanent = false) =>
    fetchAPI<void>(
      `/api/graph/node/${encodeURIComponent(nodeKey)}?case_id=${caseId}&permanent=${permanent}`,
      { method: "DELETE" }
    ),

  mergeEntities: (
    caseId: string,
    sourceKey: string,
    targetKey: string,
    mergedData?: Record<string, unknown>
  ) =>
    fetchAPI<void>("/api/graph/merge-entities", {
      method: "POST",
      body: {
        case_id: caseId,
        source_key: sourceKey,
        target_key: targetKey,
        merged_data: mergedData,
      },
    }),

  expandNodes: (caseId: string, nodeKeys: string[], depth = 1) =>
    fetchAPI<GraphData>("/api/graph/expand-nodes", {
      method: "POST",
      body: { case_id: caseId, node_keys: nodeKeys, depth },
    }),

  createRelationships: (
    relationships: { source: string; target: string; type: string }[],
    caseId: string
  ) =>
    fetchAPI<void>("/api/graph/relationships", {
      method: "POST",
      body: { relationships, case_id: caseId },
    }),

  getEntityTypes: (caseId: string) =>
    fetchAPI<string[]>(`/api/graph/entity-types?case_id=${caseId}`),
}
