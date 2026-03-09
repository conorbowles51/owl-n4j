import { fetchAPI } from "@/lib/api-client"
import type { GraphData, NodeDetail } from "@/types/graph.types"

/** Backend returns { nodes, links } — map to frontend { nodes, edges } */
type RawGraphData = { nodes: GraphData["nodes"]; links: GraphData["edges"] }
function toGraphData(raw: RawGraphData): GraphData {
  return { nodes: raw.nodes ?? [], edges: raw.links ?? [] }
}

export const graphAPI = {
  getGraph: async (params: {
    case_id: string
    start_date?: string
    end_date?: string
  }) => {
    const qs = new URLSearchParams({ case_id: params.case_id })
    if (params.start_date) qs.set("start_date", params.start_date)
    if (params.end_date) qs.set("end_date", params.end_date)
    const raw = await fetchAPI<RawGraphData>(`/api/graph?${qs}`)
    return toGraphData(raw)
  },

  getNodeDetails: (key: string, caseId: string) =>
    fetchAPI<NodeDetail>(
      `/api/graph/node/${encodeURIComponent(key)}?case_id=${caseId}`
    ),

  getNodeNeighbours: async (key: string, depth: number, caseId: string) => {
    const raw = await fetchAPI<RawGraphData>(
      `/api/graph/node/${encodeURIComponent(key)}/neighbours?depth=${depth}&case_id=${caseId}`
    )
    return toGraphData(raw)
  },

  search: async (query: string, caseId: string, limit = 20) => {
    const raw = await fetchAPI<RawGraphData>(
      `/api/graph/search?q=${encodeURIComponent(query)}&limit=${limit}&case_id=${caseId}`
    )
    return toGraphData(raw)
  },

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

  expandNodes: async (caseId: string, nodeKeys: string[], depth = 1) => {
    const raw = await fetchAPI<RawGraphData>("/api/graph/expand-nodes", {
      method: "POST",
      body: { case_id: caseId, node_keys: nodeKeys, depth },
    })
    return toGraphData(raw)
  },

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
