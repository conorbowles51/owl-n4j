import { fetchAPI } from "@/lib/api-client"
import type {
  GraphData,
  NodeDetail,
  RecycledEntity,
  SimilarPair,
  RejectedMergePair,
  PageRankResult,
  CommunityResult,
  BetweennessResult,
  ShortestPathResult,
} from "@/types/graph.types"

/* ------------------------------------------------------------------ */
/*  Raw backend shape → frontend mapping                               */
/* ------------------------------------------------------------------ */

type RawNode = Record<string, unknown>
type RawEdge = Record<string, unknown>
type RawGraphData = { nodes: RawNode[]; links: RawEdge[] }

function toGraphData(raw: RawGraphData): GraphData {
  return {
    nodes: (raw.nodes ?? []).map((n: RawNode) => ({
      key: n.key,
      label: n.name || n.label || n.key,
      type: (n.type || "").toLowerCase(),
      confidence: n.confidence,
      mentioned: n.mentioned,
      properties: n.properties ?? {},
    })),
    edges: (raw.links ?? []).map((e: RawEdge) => ({
      source: e.source,
      target: e.target,
      type: e.type || e.relationship || "",
      weight: e.weight,
    })),
  }
}

/* ------------------------------------------------------------------ */
/*  Graph API                                                          */
/* ------------------------------------------------------------------ */

export const graphAPI = {
  /* --- Graph retrieval --- */

  getGraph: async (params: {
    case_id: string
    start_date?: string
    end_date?: string
    limit?: number
    sort_by?: string
  }) => {
    const qs = new URLSearchParams({ case_id: params.case_id, lightweight: "true" })
    if (params.start_date) qs.set("start_date", params.start_date)
    if (params.end_date) qs.set("end_date", params.end_date)
    if (params.limit != null) qs.set("limit", String(params.limit))
    if (params.sort_by) qs.set("sort_by", params.sort_by)
    const raw = await fetchAPI<RawGraphData>(`/api/graph?${qs}`)
    return toGraphData(raw)
  },

  getNodeDetails: async (key: string, caseId: string) => {
    const raw = await fetchAPI<
      Record<string, unknown> & {
        connections?: { relationship?: string; key: string; name: string; type: string }[]
      }
    >(
      `/api/graph/node/${encodeURIComponent(key)}?case_id=${caseId}`
    )
    // Group flat connections into ConnectionGroup[]
    const grouped = new Map<
      string,
      { relationshipType: string; nodes: { key: string; label: string; type: string }[] }
    >()
    for (const c of raw.connections ?? []) {
      const relType = c.relationship || "RELATED_TO"
      if (!grouped.has(relType)) {
        grouped.set(relType, { relationshipType: relType, nodes: [] })
      }
      grouped.get(relType)!.nodes.push({
        key: c.key,
        label: c.name,
        type: c.type,
      })
    }
    return {
      ...raw,
      label: raw.name || raw.label || raw.key,
      connections: Array.from(grouped.values()),
    } as NodeDetail
  },

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

  getEntityTypes: (caseId: string) =>
    fetchAPI<{ entity_types: { type: string; count: number }[] }>(
      `/api/graph/entity-types?case_id=${caseId}`
    ),

  /* --- Node CRUD --- */

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

  /* --- Relationships --- */

  createRelationships: (
    relationships: { source: string; target: string; type: string }[],
    caseId: string
  ) =>
    fetchAPI<void>("/api/graph/relationships", {
      method: "POST",
      body: { relationships, case_id: caseId },
    }),

  /* --- Expand / Subgraph --- */

  expandNodes: async (caseId: string, nodeKeys: string[], depth = 1) => {
    const raw = await fetchAPI<RawGraphData>("/api/graph/expand-nodes", {
      method: "POST",
      body: { case_id: caseId, node_keys: nodeKeys, depth },
    })
    return toGraphData(raw)
  },

  getShortestPaths: (caseId: string, nodeKeys: string[], maxDepth = 10) =>
    fetchAPI<ShortestPathResult>("/api/graph/shortest-paths", {
      method: "POST",
      body: { case_id: caseId, node_keys: nodeKeys, max_depth: maxDepth },
    }),

  /* --- Entity merge / dedup --- */

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

  findSimilarEntities: (
    caseId: string,
    entityTypes?: string[] | null,
    similarityThreshold = 0.7,
    maxResults = 1000
  ) =>
    fetchAPI<{ similar_pairs: SimilarPair[] }>("/api/graph/find-similar-entities", {
      method: "POST",
      body: {
        case_id: caseId,
        entity_types: entityTypes,
        name_similarity_threshold: similarityThreshold,
        max_results: maxResults,
      },
    }),

  rejectMergePair: (caseId: string, entityKey1: string, entityKey2: string) =>
    fetchAPI<void>("/api/graph/reject-merge-pair", {
      method: "POST",
      body: { case_id: caseId, entity_key1: entityKey1, entity_key2: entityKey2 },
    }),

  getRejectedMergePairs: (caseId: string) =>
    fetchAPI<{ pairs: RejectedMergePair[] }>(
      `/api/graph/rejected-merge-pairs?case_id=${caseId}`
    ),

  undoRejection: (rejectionId: string) =>
    fetchAPI<void>(`/api/graph/rejected-merge-pairs/${rejectionId}`, {
      method: "DELETE",
    }),

  /* --- Recycle bin --- */

  listRecycledEntities: (caseId: string) =>
    fetchAPI<{ items: RecycledEntity[]; total: number }>(
      `/api/graph/recycle-bin?case_id=${encodeURIComponent(caseId)}`
    ),

  restoreRecycledEntity: (recycleKey: string, caseId: string) =>
    fetchAPI<void>(
      `/api/graph/recycle-bin/${encodeURIComponent(recycleKey)}/restore?case_id=${encodeURIComponent(caseId)}`,
      { method: "POST" }
    ),

  permanentlyDeleteRecycled: (recycleKey: string, caseId: string) =>
    fetchAPI<void>(
      `/api/graph/recycle-bin/${encodeURIComponent(recycleKey)}?case_id=${encodeURIComponent(caseId)}`,
      { method: "DELETE" }
    ),

  /* --- Graph algorithms --- */

  getPageRank: (
    caseId: string,
    nodeKeys?: string[] | null,
    topN = 20,
    iterations = 20,
    dampingFactor = 0.85
  ) =>
    fetchAPI<{ results: PageRankResult[] }>("/api/graph/pagerank", {
      method: "POST",
      body: {
        case_id: caseId,
        node_keys: nodeKeys,
        top_n: topN,
        iterations,
        damping_factor: dampingFactor,
      },
    }),

  getLouvainCommunities: (
    caseId: string,
    nodeKeys?: string[] | null,
    resolution = 1.0,
    maxIterations = 10
  ) =>
    fetchAPI<{ communities: CommunityResult[] }>("/api/graph/louvain", {
      method: "POST",
      body: {
        case_id: caseId,
        node_keys: nodeKeys,
        resolution,
        max_iterations: maxIterations,
      },
    }),

  getBetweennessCentrality: (
    caseId: string,
    nodeKeys?: string[] | null,
    topN = 20,
    normalized = true
  ) =>
    fetchAPI<{ results: BetweennessResult[] }>("/api/graph/betweenness", {
      method: "POST",
      body: {
        case_id: caseId,
        node_keys: nodeKeys,
        top_n: topN,
        normalized,
      },
    }),

  /* --- Facts & Insights --- */

  pinFact: (nodeKey: string, factIndex: number, pinned: boolean, caseId: string) =>
    fetchAPI<void>(
      `/api/graph/node/${encodeURIComponent(nodeKey)}/pin-fact`,
      { method: "PUT", body: { fact_index: factIndex, pinned, case_id: caseId } }
    ),

  verifyInsight: (
    nodeKey: string,
    insightIndex: number,
    username: string,
    caseId: string,
    sourceDoc?: string,
    page?: number
  ) =>
    fetchAPI<void>(
      `/api/graph/node/${encodeURIComponent(nodeKey)}/verify-insight`,
      {
        method: "POST",
        body: { insight_index: insightIndex, username, case_id: caseId, source_doc: sourceDoc, page },
      }
    ),

  rejectInsight: (nodeKey: string, insightIndex: number, caseId: string) =>
    fetchAPI<void>(
      `/api/graph/node/${encodeURIComponent(nodeKey)}/insights/${insightIndex}?case_id=${encodeURIComponent(caseId)}`,
      { method: "DELETE" }
    ),

  /* --- AI analysis --- */

  analyzeNodeRelationships: (nodeKey: string, caseId: string) =>
    fetchAPI<{
      suggestions: {
        target_key: string
        target_name: string
        relationship_type: string
        confidence: number
        reasoning: string
      }[]
    }>(
      `/api/graph/node/${encodeURIComponent(nodeKey)}/analyze-relationships`,
      { method: "POST", body: { case_id: caseId } }
    ),

  /* --- Geocoding --- */

  geocodeNode: (nodeKey: string, caseId: string, address: string) =>
    fetchAPI<{ lat: number; lng: number }>(
      `/api/graph/node/${encodeURIComponent(nodeKey)}/geocode`,
      { method: "POST", body: { case_id: caseId, address } }
    ),

  /* --- Cypher --- */

  executeCypher: (caseId: string, query: string) =>
    fetchAPI<{ columns: string[]; rows: unknown[][] }>("/api/graph/cypher", {
      method: "POST",
      body: { case_id: caseId, query },
    }),
}

/* ------------------------------------------------------------------ */
/*  SSE streaming for similar entities                                 */
/* ------------------------------------------------------------------ */

export interface SimilarEntitiesStreamCallbacks {
  onStart?: () => void
  onTypeStart?: (data: { type: string; count: number }) => void
  onProgress?: (data: {
    type: string
    compared: number
    total: number
    pairs_found: number
  }) => void
  onTypeComplete?: (data: { type: string; pairs: SimilarPair[] }) => void
  onComplete?: (data: { total_pairs: number; total_comparisons: number; limited_results: unknown[] }) => void
  onError?: (error: string) => void
  onCancelled?: () => void
}

export function findSimilarEntitiesStream(
  caseId: string,
  options: {
    entityTypes?: string[] | null
    similarityThreshold?: number
    maxResults?: number
  },
  callbacks: SimilarEntitiesStreamCallbacks
): () => void {
  const token = localStorage.getItem("authToken")
  const params = new URLSearchParams({ case_id: caseId })
  if (options.similarityThreshold != null)
    params.set("name_similarity_threshold", String(options.similarityThreshold))
  if (options.maxResults != null)
    params.set("max_results", String(options.maxResults))
  if (options.entityTypes?.length)
    params.set("entity_types", options.entityTypes.join(","))

  const url = `/api/graph/find-similar-entities/stream?${params}`
  const es = new EventSource(
    token ? `${url}&token=${encodeURIComponent(token)}` : url
  )

  es.addEventListener("start", () => callbacks.onStart?.())
  es.addEventListener("type_start", (e) =>
    callbacks.onTypeStart?.(JSON.parse(e.data))
  )
  es.addEventListener("progress", (e) =>
    callbacks.onProgress?.(JSON.parse(e.data))
  )
  es.addEventListener("type_complete", (e) =>
    callbacks.onTypeComplete?.(JSON.parse(e.data))
  )
  es.addEventListener("complete", (e) => {
    callbacks.onComplete?.(JSON.parse(e.data))
    es.close()
  })
  es.addEventListener("cancelled", () => {
    callbacks.onCancelled?.()
    es.close()
  })
  es.addEventListener("error", (e) => {
    callbacks.onError?.((e as MessageEvent).data ?? "Stream error")
    es.close()
  })

  return () => es.close()
}
