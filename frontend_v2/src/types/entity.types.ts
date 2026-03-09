import type { EntityType } from "@/lib/theme"

export interface Entity {
  key: string
  label: string
  type: EntityType
  properties: Record<string, unknown>
  connectionCount: number
  confidence?: number
}

export interface Relationship {
  source: string
  target: string
  type: string
  properties?: Record<string, unknown>
}
