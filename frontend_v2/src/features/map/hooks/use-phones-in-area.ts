import { useQuery } from "@tanstack/react-query"
import { getPhoneMapArea } from "@/features/phones/api"
import type { BoundingShape } from "../stores/map.store"

/** Phone positions inside a drawn area; the "Phones seen in this area" panel and the area banner share this query. */
export function usePhonesInArea(caseId: string, shape: BoundingShape | null) {
  const ring = (shape?.coordinates ?? []).map(([lng, lat]) => [lng, lat])
  return useQuery({
    queryKey: ["phone-map-area", caseId, shape?.id ?? null, ring.map((c) => c.join(",")).join(";")],
    queryFn: ({ signal }) => getPhoneMapArea(caseId, ring, {}, signal),
    enabled: shape != null,
  })
}
