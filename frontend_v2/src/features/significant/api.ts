import { fetchAPI } from "@/lib/api-client"
import type {
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

  clear: (caseId: string) =>
    fetchAPI<SignificantManifest>(
      `/api/significant/${encodeURIComponent(caseId)}`,
      { method: "DELETE" }
    ),
}
