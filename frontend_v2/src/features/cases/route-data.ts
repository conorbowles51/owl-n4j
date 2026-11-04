import type { RouteDataContext } from "@/lib/route-preload"
import { isSuperAdminUser } from "@/features/auth/auth.types"
import { useCaseManagementStore } from "./case-management.store"
import { casesListQuery } from "./hooks/use-cases"
import { snapshotsQuery } from "./hooks/use-snapshots"

/** The case list's first data (CaseListSidebar's case list, CaseDetailPanel's snapshots), same keys and fetchers. */
export function prefetch({ client, user }: RouteDataContext) {
  // As CaseListSidebar: a super admin's list follows the chosen view; archived cases are hidden when it opens.
  const viewMode = isSuperAdminUser(user) ? useCaseManagementStore.getState().viewMode : undefined
  void client.prefetchQuery(casesListQuery(viewMode, false))
  void client.prefetchQuery(snapshotsQuery())
}
