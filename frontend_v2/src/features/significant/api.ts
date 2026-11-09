import { fetchAPI } from "@/lib/api-client"
import type {
  RelationshipRef,
  SignificantAdditionSource,
  SignificantManifest,
} from "./types"

export const significantAPI = {
  getManifest: (caseId: string) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}`
    ),

  addEntities: (
    caseId: string,
    entityKeys: string[],
    source: SignificantAdditionSource,
    context: Record<string, unknown> = {}
  ) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}/entities:batch`,
      {
        method: "POST",
        body: {
          entity_keys: entityKeys,
          source,
          context,
        },
      }
    ),

  removeEntities: (caseId: string, entityKeys: string[]) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}/entities:remove`,
      {
        method: "POST",
        body: { entity_keys: entityKeys },
      }
    ),

  addRelationships: (
    caseId: string,
    relationships: RelationshipRef[],
    source: SignificantAdditionSource,
    context: Record<string, unknown> = {}
  ) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}/relationships:batch`,
      { method: "POST", body: { relationships, source, context } }
    ),

  removeRelationships: (caseId: string, relationships: RelationshipRef[]) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}/relationships:remove`,
      { method: "POST", body: { relationships } }
    ),

  clear: (caseId: string) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}`,
      { method: "DELETE" }
    ),
}
