export type CaseLayer = "all" | "significant"

export type SignificantAdditionSource =
  | "manual"
  | "selection"
  | "spotlight"
  | "agent"
  | "migration"

export interface SignificantItem {
  id: string
  case_id: string
  entity_key: string
  addition_source: SignificantAdditionSource | string
  context: Record<string, unknown>
  added_by_user_id?: string | null
  added_by_name?: string | null
  added_by_email?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface SignificantManifest {
  case_id: string
  entity_keys: string[]
  items: SignificantItem[]
  count: number
  added_count?: number | null
  already_significant_count?: number | null
  missing_count?: number | null
  added_entity_keys?: string[] | null
  missing_entity_keys?: string[] | null
  removed_count?: number | null
  not_significant_count?: number | null
  removed_entity_keys?: string[] | null
}
