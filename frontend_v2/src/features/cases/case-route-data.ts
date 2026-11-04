import type { RouteDataContext } from "@/lib/route-preload"
import { phonesQuery } from "@/features/phones/phones-query"
import { significantManifestQuery } from "@/features/significant/hooks/use-significant"

/**
 * What every case page's sidebar asks for first (its layers and its phones), started at start-up with the page's
 * own first data. Same keys and fetchers as the sidebar's queries.
 */
export function prefetchCaseShell({ client, params }: RouteDataContext) {
  const caseId = params.id
  if (!caseId) return
  void client.prefetchQuery(significantManifestQuery(caseId))
  void client.prefetchQuery(phonesQuery(caseId))
}
