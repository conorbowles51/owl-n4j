import { getProfile, getSettings, getThreads, type StreamFilter, type ThreadSort } from "./api"
import { keptResults } from "./analysis/analysis-api"

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
