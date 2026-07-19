import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

export interface FileEntity {
  id: string
  key: string | null
  node_key?: string | null
  name: string
  category: string
  specific_type: string
  confidence: number
  latitude?: number | null
  longitude?: number | null
  location_raw?: string | null
  location_formatted?: string | null
  location_name?: string | null
  geocoding_confidence?: string | null
  location_source?: string | null
  location_corrected_at?: string | null
  location_corrected_by?: string | null
  location_correction_source?: string | null
  location_correction_address?: string | null
  last_location_relocation_key?: string | null
}

export interface FileRelationship {
  source_entity_name: string
  target_entity_name: string
  type: string
  detail: string
  confidence: number
}

export function useFileEntities(evidenceId: string | null) {
  return useQuery({
    queryKey: ["evidence-file-entities", evidenceId],
    queryFn: async () => {
      return fetchAPI<FileEntity[]>(`/api/evidence/${evidenceId}/entities`)
    },
    enabled: !!evidenceId,
  })
}

export function useFileRelationships(evidenceId: string | null) {
  return useQuery({
    queryKey: ["evidence-file-relationships", evidenceId],
    queryFn: async () => {
      return fetchAPI<FileRelationship[]>(`/api/evidence/${evidenceId}/relationships`)
    },
    enabled: !!evidenceId,
  })
}
