import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  cellebriteAPI,
  cellebriteCommsAPI,
  cellebriteEventsAPI,
  cellebriteFilesAPI,
  cellebriteOverviewAPI,
  evidenceCellebriteAPI,
} from "../api"
import type {
  CommsFilterParams,
  DateRangeParams,
  OverviewKind,
  PagedParams,
  ReportScopedParams,
} from "../types"

export const cellebriteKeys = {
  all: ["cellebrite"] as const,
  reports: (caseId: string | undefined) =>
    [...cellebriteKeys.all, "reports", caseId] as const,
  timeline: (caseId: string | undefined, params: unknown) =>
    [...cellebriteKeys.all, "timeline", caseId, params] as const,
  graph: (caseId: string | undefined) =>
    [...cellebriteKeys.all, "graph", caseId] as const,
  network: (caseId: string | undefined) =>
    [...cellebriteKeys.all, "network", caseId] as const,
  comms: (caseId: string | undefined, name: string, params: unknown) =>
    [...cellebriteKeys.all, "comms", name, caseId, params] as const,
  events: (caseId: string | undefined, name: string, params: unknown) =>
    [...cellebriteKeys.all, "events", name, caseId, params] as const,
  overview: (
    caseId: string | undefined,
    reportKey: string | undefined,
    kind: OverviewKind,
    params: unknown
  ) =>
    [
      ...cellebriteKeys.all,
      "overview",
      kind,
      caseId,
      reportKey,
      params,
    ] as const,
  files: (caseId: string | undefined, name: string, params: unknown) =>
    [...cellebriteKeys.all, "files", name, caseId, params] as const,
}

export function useCellebriteReports(caseId: string | undefined) {
  return useQuery({
    queryKey: cellebriteKeys.reports(caseId),
    queryFn: () => cellebriteAPI.getReports(caseId!),
    enabled: !!caseId,
    staleTime: 1500,
  })
}

export function usePatchCellebriteReport(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportKey,
      deviceNameOverride,
    }: {
      reportKey: string
      deviceNameOverride: string | null
    }) =>
      cellebriteAPI.patchReport(caseId, reportKey, {
        device_name_override: deviceNameOverride,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: cellebriteKeys.reports(caseId),
      })
    },
  })
}

export function useDeleteCellebriteReport(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (reportKey: string) =>
      cellebriteAPI.deleteReport(caseId, reportKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cellebriteKeys.all })
      queryClient.invalidateQueries({ queryKey: ["background-tasks", caseId] })
      queryClient.invalidateQueries({ queryKey: ["background-tasks"] })
    },
  })
}

export function useCellebriteTimeline(
  caseId: string | undefined,
  reportKeys: string[] | null,
  params: DateRangeParams & PagedParams & { eventTypes?: string[] | null },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.timeline(caseId, { reportKeys, params }),
    queryFn: () => cellebriteAPI.getTimeline(caseId!, reportKeys, params),
    enabled: !!caseId && enabled,
  })
}

export function useCellebriteCrossPhoneGraph(
  caseId: string | undefined,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.graph(caseId),
    queryFn: () => cellebriteAPI.getCrossPhoneGraph(caseId!),
    enabled: !!caseId && enabled,
  })
}

export function useCellebriteCommunicationNetwork(
  caseId: string | undefined,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.network(caseId),
    queryFn: () => cellebriteAPI.getCommunicationNetwork(caseId!),
    enabled: !!caseId && enabled,
  })
}

export function useCommsEntities(
  caseId: string | undefined,
  reportKeys: string[] | null,
  enabled = true,
  withCounts = false
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "entities", {
      reportKeys,
      withCounts,
    }),
    queryFn: () =>
      cellebriteCommsAPI.getEntities(caseId!, reportKeys, { withCounts }),
    enabled: !!caseId && enabled,
  })
}

export function useCommsSourceApps(
  caseId: string | undefined,
  reportKeys: string[] | null,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "source-apps", { reportKeys }),
    queryFn: () => cellebriteCommsAPI.getSourceApps(caseId!, reportKeys),
    enabled: !!caseId && enabled,
  })
}

export function useCommsThreads(
  caseId: string | undefined,
  params: CommsFilterParams,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "threads", params),
    queryFn: () => cellebriteCommsAPI.getThreads(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useThreadDetail(
  caseId: string | undefined,
  thread: { thread_id: string; thread_type: string } | null,
  params: PagedParams & { anchorKey?: string | null },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "thread-detail", { thread, params }),
    queryFn: () =>
      cellebriteCommsAPI.getThreadDetail(
        caseId!,
        thread!.thread_id,
        thread!.thread_type,
        params
      ),
    enabled: !!caseId && !!thread && enabled,
  })
}

export function useCommsBetween(
  caseId: string | undefined,
  params: CommsFilterParams,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "between", params),
    queryFn: () => cellebriteCommsAPI.getBetween(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useCommsEnvelope(
  caseId: string | undefined,
  params: CommsFilterParams,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "envelope", params),
    queryFn: () => cellebriteCommsAPI.getEnvelope(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useContactCommsFeed(
  caseId: string | undefined,
  contactKey: string | undefined,
  params: ReportScopedParams & PagedParams & { types?: string[] | null },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "contact-feed", {
      contactKey,
      params,
    }),
    queryFn: () =>
      cellebriteCommsAPI.getContactFeed(caseId!, contactKey!, params),
    enabled: !!caseId && !!contactKey && enabled,
  })
}

export function useMessageSearch(
  caseId: string | undefined,
  params: { q: string; reportKeys?: string[] | null; limit?: number },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.comms(caseId, "message-search", params),
    queryFn: () => cellebriteCommsAPI.searchMessages(caseId!, params),
    enabled: !!caseId && enabled && params.q.trim().length > 0,
  })
}

export function useEventTypes(
  caseId: string | undefined,
  reportKeys: string[] | null,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "types", { reportKeys }),
    queryFn: () => cellebriteEventsAPI.getEventTypes(caseId!, reportKeys),
    enabled: !!caseId && enabled,
  })
}

export function useEvents(
  caseId: string | undefined,
  params: ReportScopedParams &
    DateRangeParams &
    PagedParams & {
      eventTypes?: string[] | null
      sourceApps?: string[] | null
      onlyGeolocated?: boolean
    },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "feed", params),
    queryFn: () => cellebriteEventsAPI.getEvents(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useLocationTiles(
  caseId: string | undefined,
  params: ReportScopedParams &
    DateRangeParams & {
      zoom?: number
      bbox?: [number, number, number, number] | null
    },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "tiles", params),
    queryFn: () => cellebriteEventsAPI.getLocationTiles(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useLocationsInTile(
  caseId: string | undefined,
  params:
    | (ReportScopedParams &
        DateRangeParams & {
          cellX: number
          cellY: number
          cellDeg: number
          limit?: number
        })
    | null,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "in-tile", params),
    queryFn: () => cellebriteEventsAPI.getLocationsInTile(caseId!, params!),
    enabled: !!caseId && !!params && enabled,
  })
}

export function useEventTracks(
  caseId: string | undefined,
  params: ReportScopedParams & DateRangeParams & { simplify?: boolean },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "tracks", params),
    queryFn: () => cellebriteEventsAPI.getTracks(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useEventDetail(
  caseId: string | undefined,
  nodeKey: string | null,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "detail", { nodeKey }),
    queryFn: () => cellebriteEventsAPI.getEventDetail(caseId!, nodeKey!),
    enabled: !!caseId && !!nodeKey && enabled,
  })
}

export function useEventRelated(
  caseId: string | undefined,
  nodeKey: string | null,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "related", { nodeKey }),
    queryFn: () => cellebriteEventsAPI.getEventRelated(caseId!, nodeKey!),
    enabled: !!caseId && !!nodeKey && enabled,
  })
}

export function useUnifiedContacts(
  caseId: string | undefined,
  params: ReportScopedParams & PagedParams & { search?: string | null },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.events(caseId, "unified-contacts", params),
    queryFn: () => cellebriteEventsAPI.getUnifiedContacts(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useRunIntersections(caseId: string) {
  return useMutation({
    mutationFn: (body: {
      methods: string[]
      reportKeys?: string[] | null
      startDate?: string | null
      endDate?: string | null
      params?: Record<string, unknown> | null
    }) => cellebriteEventsAPI.runIntersections(caseId, body),
  })
}

export function useOverviewRows(
  kind: OverviewKind,
  caseId: string | undefined,
  reportKey: string | undefined,
  params: PagedParams & { search?: string | null },
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.overview(caseId, reportKey, kind, params),
    queryFn: () =>
      cellebriteOverviewAPI.getRows(kind, caseId!, reportKey!, params),
    enabled: !!caseId && !!reportKey && enabled,
  })
}

export function useOverviewContactDetail(
  caseId: string | undefined,
  reportKey: string | undefined,
  contactKey: string | undefined,
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.overview(caseId, reportKey, "contacts", {
      contactKey,
    }),
    queryFn: () =>
      cellebriteOverviewAPI.getContactDetail(caseId!, reportKey!, contactKey!),
    enabled: !!caseId && !!reportKey && !!contactKey && enabled,
  })
}

export function useCellebriteFiles(
  caseId: string | undefined,
  params: Parameters<typeof cellebriteFilesAPI.list>[1],
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.files(caseId, "list", params),
    queryFn: () => cellebriteFilesAPI.list(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useCellebriteFilesTree(
  caseId: string | undefined,
  params: Parameters<typeof cellebriteFilesAPI.tree>[1],
  enabled = true
) {
  return useQuery({
    queryKey: cellebriteKeys.files(caseId, "tree", params),
    queryFn: () => cellebriteFilesAPI.tree(caseId!, params),
    enabled: !!caseId && enabled,
  })
}

export function useCheckCellebriteFolder(caseId: string) {
  return useMutation({
    mutationFn: (folderPath: string) =>
      evidenceCellebriteAPI.checkFolder(caseId, folderPath),
  })
}

export function useProcessCellebriteFolder(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      folderPath,
      force,
      replaceExisting,
    }: {
      folderPath: string
      force?: boolean
      replaceExisting?: boolean
    }) =>
      evidenceCellebriteAPI.processFolder(caseId, folderPath, {
        force,
        replaceExisting,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cellebriteKeys.all })
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
    },
  })
}
