import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

export interface FileEntity {
  id: string
  name: string
  category: string
  specific_type: string
  confidence: number
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
