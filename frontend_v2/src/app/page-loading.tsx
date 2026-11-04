import { useLocation } from "react-router-dom"
import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { routePage } from "@/lib/route-speed"

/**
 * The fallback of every lazy route page while its code arrives: the shared loading panel for the page the address
 * names (the step in words, true counts, time left), never a bare spinner (page-speed standard: data or a progress
 * panel within 2 s). The page's own reads continue in the same panel once its code has arrived.
 */
export function PageLoading() {
  const { pathname } = useLocation()
  const { page, caseId } = routePage(pathname)
  return <LoadProgress caseId={caseId} page={page ?? "other"} />
}
