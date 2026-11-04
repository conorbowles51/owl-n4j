import type { RouteDataContext } from "@/lib/route-preload"
import { prefetchCaseShell } from "@/features/cases/case-route-data"
import { caseQuery } from "@/features/cases/hooks/use-cases"
import { collectTargetsQuery } from "./hooks/use-collect"
import { mediaFilter, mediaIndexQuery, mediaPhoneIndexQuery, mediaWindowQuery } from "./media/media-queries"
import { conversationList, keptResultsQuery, phoneProfileQuery, phoneSettingsQuery, phoneThreadsQuery } from "./phone-queries"

/** The Phones page: the case's phones (the sidebar's query; not when the address forwards somewhere else). */
export function prefetchPhones(context: RouteDataContext) {
  if ([...context.search.keys()].length) return
  prefetchCaseShell(context)
}

/** Phone analyses: the kept results list. */
export function prefetchAnalyses(context: RouteDataContext) {
  const caseId = context.params.id
  if (!caseId) return
  prefetchCaseShell(context)
  void context.client.prefetchQuery(keptResultsQuery(caseId))
}

/** A phone's summary: its profile. */
export function prefetchSummary(context: RouteDataContext) {
  const { id: caseId, extraction } = context.params
  if (!caseId || !extraction) return
  prefetchCaseShell(context)
  void context.client.prefetchQuery(phoneProfileQuery(caseId, extraction))
}

/** A phone's media: the grid's counts and first window for the address's thread (no category or state chosen). */
export function prefetchMedia(context: RouteDataContext) {
  const { client, params, search } = context
  const { id: caseId, extraction } = params
  if (!caseId || !extraction) return
  prefetchCaseShell(context)
  const filter = mediaFilter(caseId, extraction, search.get("thread"), "", "")
  void client.prefetchQuery(mediaIndexQuery(filter))
  void client.prefetchQuery(mediaPhoneIndexQuery(caseId, extraction))
  void client.prefetchInfiniteQuery(mediaWindowQuery(filter))
}

/**
 * A phone's conversations: the case, the targets Add to… offers, the phone settings, then (as the page does, once
 * the settings have answered, for their time zone) the conversation list for the address's view.
 */
export function prefetchConversations(context: RouteDataContext) {
  const { client, params, search } = context
  const caseId = params.id
  if (!caseId) return
  prefetchCaseShell(context)
  void client.prefetchQuery(caseQuery(caseId))
  void client.prefetchQuery(collectTargetsQuery(caseId))
  void client.fetchQuery(phoneSettingsQuery(caseId)).then((settings) => {
    const { view, listFilter } = conversationList(caseId, `?${search}`, params.extraction ?? null, settings.effective.name ?? "UTC")
    void client.prefetchQuery(phoneThreadsQuery(listFilter, view.threadSort))
  }, () => {})
}
