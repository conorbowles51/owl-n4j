import type { RouteDataContext } from "@/lib/route-preload"
import { prefetchCaseShell } from "@/features/cases/case-route-data"
import { financialCategoriesQuery, financialEntitiesQuery } from "./hooks/use-financial-data"
import { judgementCountsQuery } from "./hooks/use-judgements"
import { ledgerAccountDirectoryQuery } from "./hooks/use-ledger-account-directory"
import { ledgerOverviewPanelsQuery, ledgerOverviewQuery } from "./hooks/use-ledger-overview"
import { paymentCategoriesNow } from "./hooks/use-payment-categories"
import { initialFinancialView } from "./hooks/use-financial-view-navigation"
import { financialCaseAccessQuery } from "./lib/financial-access-query"
import { overviewCoverageQuery } from "./lib/statement-coverage"
import { investigationScopeNow } from "./stores/investigation-scope"

/**
 * Financial's first data, with the keys and fetchers the page uses: the page's access check, categories and
 * entities, and, when the visit opens on the Overview (the address's view, else the last one used, else Overview),
 * the Overview's figures, panels, coverage, account directory and judgement counts for the scope and categories
 * it will show.
 */
export function prefetch(context: RouteDataContext) {
  const { client, params, search, user } = context
  const caseId = params.id
  if (!caseId) return
  prefetchCaseShell(context)
  void client.prefetchQuery(financialCaseAccessQuery(caseId, user))
  void client.prefetchQuery(financialCategoriesQuery(caseId, "transactions"))
  void client.prefetchQuery(financialEntitiesQuery(caseId))
  if (initialFinancialView(caseId, search) !== "overview") return
  const scope = investigationScopeNow(caseId)
  const categories = paymentCategoriesNow(caseId)
  void client.prefetchQuery(ledgerOverviewQuery(caseId, scope, categories))
  void client.prefetchQuery(ledgerOverviewPanelsQuery(caseId, scope, categories))
  void client.prefetchQuery(overviewCoverageQuery(caseId, 0))
  void client.prefetchQuery(ledgerAccountDirectoryQuery(caseId))
  void client.prefetchQuery(judgementCountsQuery(caseId))
}
