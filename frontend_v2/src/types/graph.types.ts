import type { EntityType } from "@/lib/theme"

export interface GraphNode {
  key: string
  label: string
  type: EntityType
  properties: Record<string, unknown>
  x?: number
  y?: number
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  properties?: Record<string, unknown>
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface NodeDetail {
  key: string
  label: string
  type: EntityType
  properties: Record<string, unknown>
  connections: ConnectionGroup[]
  sources: SourceReference[]
  confidence?: number
}

export interface ConnectionGroup {
  relationshipType: string
  nodes: { key: string; label: string; type: EntityType }[]
}

export interface SourceReference {
  fileId: string
  fileName: string
  excerpt?: string
}
