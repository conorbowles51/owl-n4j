import { getProfile, getSettings, getThreads, type StreamFilter, type ThreadSort } from "./api"
import { keptResults } from "./analysis/analysis-api"
import { viewFromSearch, viewToFilter } from "./lib/filter-url"

/** Keys and fetchers shared by the phone pages and the start-up prefetch (route-data.ts). */
export const phoneProfileQuery = (caseId: string, extraction: string) => ({
  queryKey: ["phone-profile", caseId, extraction],
  queryFn: () => getProfile(caseId, extraction),
})

export const keptResultsQuery = (caseId: string) => ({
  queryKey: ["phone-analysis-kept-list", caseId],
  queryFn: () => keptResults(caseId),
})

export const phoneSettingsQuery = (caseId: string) => ({
  queryKey: ["phone-settings", caseId],
  queryFn: () => getSettings(caseId),
})

export const phoneThreadsQuery = (listFilter: StreamFilter, sort: ThreadSort) => ({
  queryKey: ["phone-threads", listFilter, sort],
  queryFn: () => getThreads(listFilter, sort),
})

/** The conversation list's filter and sort for an address (ConversationsPage and the start-up prefetch). */
export function conversationList(caseId: string, search: string, fixedPhone: string | null, zoneName: string) {
  const view = viewFromSearch(search, fixedPhone)
  return { view, listFilter: viewToFilter(caseId, view, zoneName, false) }
}
