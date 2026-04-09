export interface GraphNode {
  key: string
  label: string
  type: string
  summary?: string
  notes?: string
  verified_facts?: VerifiedFact[]
  ai_insights?: AIInsight[]
  confidence?: number
  community_id?: number
  mentioned?: boolean
  properties: Record<string, unknown>
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

export interface VerifiedFact {
  text: string
  pinned?: boolean
  source_doc?: string
  page?: number
  citations?: string[]
}

export interface AIInsight {
  text: string
  confidence?: number
  verified?: boolean
  verified_by?: string
  rejected?: boolean
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  weight?: number
  properties?: Record<string, unknown>
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface NodeDetail {
  key: string
  label: string
  type: string
  summary?: string
  notes?: string
  verified_facts?: VerifiedFact[]
  ai_insights?: AIInsight[]
  properties: Record<string, unknown>
  connections: ConnectionGroup[]
  sources: SourceReference[]
  confidence?: number
}

export interface ConnectionGroup {
  relationshipType: string
  nodes: { key: string; label: string; type: string }[]
}

export interface SourceReference {
  fileId: string
  fileName: string
  excerpt?: string
}

export interface RecycledEntity {
  key: string
  original_key: string
  original_name: string
  type: string
  deleted_at: string
  reason: string
  relationship_count: number
  deleted_by?: string
}

export interface SimilarPair {
  key1: string
  name1: string
  type1: string
  key2: string
  name2: string
  type2: string
  similarity: number
}

export interface RejectedMergePair {
  id: string
  entity_key1: string
  entity_key2: string
  rejected_at: string
}

export interface PageRankResult {
  key: string
  name: string
  type: string
  score: number
}

export interface CommunityResult {
  community_id: number
  nodes: { key: string; name: string; type: string }[]
  size: number
}

export interface BetweennessResult {
  key: string
  name: string
  type: string
  score: number
}

export interface ShortestPathResult {
  paths: { nodes: string[]; edges: string[]; length: number }[]
}
