import type { RouteDataContext } from "@/lib/route-preload"
import { prefetchCaseShell } from "@/features/cases/case-route-data"
import { caseQuery } from "@/features/cases/hooks/use-cases"
import { financialCaseAccessQuery } from "@/features/financial/lib/financial-access-query"
import { useEvidenceStore } from "./evidence.store"
import { caseProcessingProfileQuery } from "./hooks/use-case-processing-profile"
import { folderContentsParams, folderContentsQuery } from "./hooks/use-folder-contents"
import { folderTreeQuery } from "./hooks/use-folder-tree"

/**
 * Evidence's first data, with the keys and fetchers the page uses: the folder tree, the case, its processing
 * profile and access check, and the top folder's first page of files in the person's saved sort (not when the
 * address opens a particular file: that page is found first).
 */
export function prefetch(context: RouteDataContext) {
  const { client, params, search, user } = context
  const caseId = params.id
  if (!caseId) return
  prefetchCaseShell(context)
  void client.prefetchQuery(folderTreeQuery(caseId))
  void client.prefetchQuery(caseQuery(caseId))
  void client.prefetchQuery(caseProcessingProfileQuery(caseId))
  void client.prefetchQuery(financialCaseAccessQuery(caseId, user))
  if (search.get("file")) return
  // EvidenceExplorer opens the case at its top folder, first page (resetForCase); filters start empty.
  const list = useEvidenceStore.getState()
  const start = { ...list, filePage: 0 }
  void client.prefetchQuery(folderContentsQuery(caseId, null, folderContentsParams(start)))
}
