import { fetchAPI } from "@/lib/api-client"
import type {
  Attachment,
  CellebriteRecord,
  CommsBetweenResponse,
  CommsEnvelopeResponse,
  CommsFilterParams,
  CommsSourceApp,
  CommsThreadsResponse,
  CommunicationNetworkResponse,
  CrossPhoneGraphResponse,
  DateRangeParams,
  DeleteReportResponse,
  EventRelatedResponse,
  EventTrack,
  EventTracksResponse,
  EventTypeCount,
  EventsResponse,
  FileTreeResponse,
  FilesResponse,
  IntersectionRunResponse,
  LocationTilesResponse,
  LocationsInTileResponse,
  OverviewKind,
  OverviewResponse,
  PagedParams,
  PhoneReport,
  PhoneReportsResponse,
  ReportScopedParams,
  SearchMessagesResponse,
  ThreadDetailResponse,
  TimelineResponse,
  UnifiedContactsResponse,
} from "./types"

function appendCsv(params: URLSearchParams, name: string, values?: string[] | null) {
  if (values?.length) params.set(name, values.join(","))
}

function appendDateRange(params: URLSearchParams, opts: DateRangeParams) {
  if (opts.startDate) params.set("start_date", opts.startDate)
  if (opts.endDate) params.set("end_date", opts.endDate)
}

function appendPaging(params: URLSearchParams, opts: PagedParams, defaults: Required<PagedParams>) {
  params.set("limit", String(opts.limit ?? defaults.limit))
  params.set("offset", String(opts.offset ?? defaults.offset))
}

function baseCaseParams(caseId: string, reportKeys?: string[] | null) {
  const params = new URLSearchParams({ case_id: caseId })
  appendCsv(params, "report_keys", reportKeys)
  return params
}

function commsParams(caseId: string, opts: CommsFilterParams = {}) {
  const params = baseCaseParams(caseId, opts.reportKeys)
  appendCsv(params, "from_keys", opts.fromKeys)
  appendCsv(params, "to_keys", opts.toKeys)
  appendCsv(params, "participant_keys", opts.participantKeys)
  appendCsv(params, "thread_types", opts.threadTypes)
  appendCsv(params, "source_apps", opts.sourceApps)
  appendCsv(params, "types", opts.types)
  appendDateRange(params, opts)
  if (opts.search) params.set("search", opts.search)
  return params
}

function overviewParams(caseId: string, reportKey: string, opts: PagedParams & { search?: string | null }) {
  const params = new URLSearchParams({ case_id: caseId, report_key: reportKey })
  if (opts.search) params.set("search", opts.search)
  appendPaging(params, opts, { limit: 500, offset: 0 })
  return params
}

export const cellebriteAPI = {
  getReports: (caseId: string) =>
    fetchAPI<PhoneReportsResponse>(`/api/cellebrite/reports?case_id=${encodeURIComponent(caseId)}`),

  deleteReport: (caseId: string, reportKey: string) =>
    fetchAPI<DeleteReportResponse>(
      `/api/cellebrite/reports/${encodeURIComponent(reportKey)}?case_id=${encodeURIComponent(caseId)}`,
      { method: "DELETE" }
    ),

  patchReport: (
    caseId: string,
    reportKey: string,
    body: Pick<PhoneReport, "device_name_override">
  ) =>
    fetchAPI<PhoneReport>(
      `/api/cellebrite/reports/${encodeURIComponent(reportKey)}?case_id=${encodeURIComponent(caseId)}`,
      { method: "PATCH", body }
    ),

  getCrossPhoneGraph: (caseId: string) =>
    fetchAPI<CrossPhoneGraphResponse>(
      `/api/cellebrite/cross-phone-graph?case_id=${encodeURIComponent(caseId)}`
    ),

  getCommunicationNetwork: (caseId: string) =>
    fetchAPI<CommunicationNetworkResponse>(
      `/api/cellebrite/communication-network?case_id=${encodeURIComponent(caseId)}`
    ),

  getTimeline: (
    caseId: string,
    reportKeys: string[] | null,
    opts: DateRangeParams & PagedParams & { eventTypes?: string[] | null } = {}
  ) => {
    const params = baseCaseParams(caseId, reportKeys)
    appendDateRange(params, opts)
    appendCsv(params, "event_types", opts.eventTypes)
    appendPaging(params, opts, { limit: 200, offset: 0 })
    return fetchAPI<TimelineResponse>(`/api/cellebrite/timeline?${params}`)
  },
}

export const cellebriteCommsAPI = {
  getEntities: (
    caseId: string,
    reportKeys: string[] | null,
    opts: { withCounts?: boolean } = {}
  ) => {
    const params = baseCaseParams(caseId, reportKeys)
    if (opts.withCounts) params.set("with_counts", "true")
    return fetchAPI<{ entities: CellebriteRecord[] }>(
      `/api/cellebrite/comms/entities?${params}`
    )
  },

  getSourceApps: (caseId: string, reportKeys?: string[] | null) => {
    const params = baseCaseParams(caseId, reportKeys)
    return fetchAPI<{ apps: CommsSourceApp[] }>(
      `/api/cellebrite/comms/source-apps?${params}`
    )
  },

  getThreads: (caseId: string, opts: CommsFilterParams = {}) => {
    const params = commsParams(caseId, opts)
    appendPaging(params, opts, { limit: 200, offset: 0 })
    return fetchAPI<CommsThreadsResponse>(`/api/cellebrite/comms/threads?${params}`)
  },

  getThreadDetail: (
    caseId: string,
    threadId: string,
    threadType: string,
    opts: PagedParams & { anchorKey?: string | null } = {}
  ) => {
    const params = new URLSearchParams({ case_id: caseId, thread_type: threadType })
    appendPaging(params, opts, { limit: 500, offset: 0 })
    if (opts.anchorKey) params.set("anchor_key", opts.anchorKey)
    return fetchAPI<ThreadDetailResponse>(
      `/api/cellebrite/comms/threads/${encodeURIComponent(threadId)}?${params}`
    )
  },

  getBetween: (caseId: string, opts: CommsFilterParams = {}) => {
    const params = commsParams(caseId, opts)
    params.set("limit", String(opts.limit ?? 500))
    if (opts.cursor) params.set("cursor", opts.cursor)
    else params.set("offset", String(opts.offset ?? 0))
    if (opts.sort) params.set("sort", opts.sort)
    return fetchAPI<CommsBetweenResponse>(`/api/cellebrite/comms/between?${params}`)
  },

  getEnvelope: (caseId: string, opts: CommsFilterParams = {}) =>
    fetchAPI<CommsEnvelopeResponse>(
      `/api/cellebrite/comms/envelope?${commsParams(caseId, opts)}`
    ),

  searchMessages: (
    caseId: string,
    opts: { q: string; reportKeys?: string[] | null; limit?: number }
  ) => {
    const params = new URLSearchParams({ case_id: caseId, q: opts.q })
    appendCsv(params, "report_keys", opts.reportKeys)
    params.set("limit", String(opts.limit ?? 200))
    return fetchAPI<SearchMessagesResponse>(
      `/api/cellebrite/comms/messages/search?${params}`
    )
  },

  resolveAttachment: (caseId: string, fileId: string) =>
    fetchAPI<Attachment>(
      `/api/cellebrite/comms/attachment/${encodeURIComponent(fileId)}?case_id=${encodeURIComponent(caseId)}`
    ),

  getContactFeed: (
    caseId: string,
    contactKey: string,
    opts: ReportScopedParams & PagedParams & { types?: string[] | null } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    appendCsv(params, "types", opts.types)
    appendPaging(params, opts, { limit: 1000, offset: 0 })
    return fetchAPI<CommsBetweenResponse>(
      `/api/cellebrite/comms/contact-feed/${encodeURIComponent(contactKey)}?${params}`
    )
  },
}

export const cellebriteEventsAPI = {
  getEventTypes: (caseId: string, reportKeys?: string[] | null) => {
    const params = baseCaseParams(caseId, reportKeys)
    return fetchAPI<{ types: EventTypeCount[] }>(
      `/api/cellebrite/events/types?${params}`
    )
  },

  getEvents: (
    caseId: string,
    opts: ReportScopedParams &
      DateRangeParams &
      PagedParams & {
        eventTypes?: string[] | null
        sourceApps?: string[] | null
        onlyGeolocated?: boolean
      } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    appendCsv(params, "event_types", opts.eventTypes)
    appendCsv(params, "source_apps", opts.sourceApps)
    appendDateRange(params, opts)
    if (opts.onlyGeolocated) params.set("only_geolocated", "true")
    appendPaging(params, opts, { limit: 5000, offset: 0 })
    return fetchAPI<EventsResponse>(`/api/cellebrite/events?${params}`)
  },

  getLocationTiles: (
    caseId: string,
    opts: ReportScopedParams &
      DateRangeParams & { zoom?: number; bbox?: [number, number, number, number] | null } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    params.set("zoom", String(opts.zoom ?? 6))
    appendDateRange(params, opts)
    if (opts.bbox) params.set("bbox", opts.bbox.join(","))
    return fetchAPI<LocationTilesResponse>(`/api/cellebrite/locations/tiles?${params}`)
  },

  getLocationsInTile: (
    caseId: string,
    opts: ReportScopedParams &
      DateRangeParams & {
        cellX: number
        cellY: number
        cellDeg: number
        limit?: number
      }
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    params.set("cell_x", String(opts.cellX))
    params.set("cell_y", String(opts.cellY))
    params.set("cell_deg", String(opts.cellDeg))
    params.set("limit", String(opts.limit ?? 200))
    appendDateRange(params, opts)
    return fetchAPI<LocationsInTileResponse>(
      `/api/cellebrite/locations/in-tile?${params}`
    )
  },

  getTracks: (
    caseId: string,
    opts: ReportScopedParams & DateRangeParams & { simplify?: boolean } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    appendDateRange(params, opts)
    params.set("simplify", opts.simplify === false ? "false" : "true")
    return fetchAPI<EventTracksResponse>(`/api/cellebrite/events/tracks?${params}`)
  },

  getEventDetail: (caseId: string, nodeKey: string) =>
    fetchAPI<TimelineResponse>(
      `/api/cellebrite/events/detail/${encodeURIComponent(nodeKey)}?case_id=${encodeURIComponent(caseId)}`
    ),

  getEventRelated: (
    caseId: string,
    nodeKey: string,
    opts: { windowH?: number; limit?: number } = {}
  ) =>
    fetchAPI<EventRelatedResponse>(
      `/api/cellebrite/events/${encodeURIComponent(nodeKey)}/related?case_id=${encodeURIComponent(caseId)}&window_h=${opts.windowH ?? 24}&limit=${opts.limit ?? 50}`
    ),

  getUnifiedContacts: (
    caseId: string,
    opts: ReportScopedParams & PagedParams & { search?: string | null } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    if (opts.search) params.set("search", opts.search)
    appendPaging(params, opts, { limit: 500, offset: 0 })
    return fetchAPI<UnifiedContactsResponse>(
      `/api/cellebrite/contacts/unified?${params}`
    )
  },

  runIntersections: (
    caseId: string,
    body: {
      methods: string[]
      reportKeys?: string[] | null
      startDate?: string | null
      endDate?: string | null
      params?: CellebriteRecord | null
    }
  ) =>
    fetchAPI<IntersectionRunResponse>(
      `/api/cellebrite/intersections/run?case_id=${encodeURIComponent(caseId)}`,
      {
        method: "POST",
        body: {
          methods: body.methods,
          report_keys: body.reportKeys,
          start_date: body.startDate,
          end_date: body.endDate,
          params: body.params,
        },
      }
    ),
}

export const cellebriteOverviewAPI = {
  getRows: (
    kind: OverviewKind,
    caseId: string,
    reportKey: string,
    opts: PagedParams & { search?: string | null } = {}
  ) =>
    fetchAPI<OverviewResponse>(
      `/api/cellebrite/overview/${kind}?${overviewParams(caseId, reportKey, opts)}`
    ),

  getContactDetail: (caseId: string, reportKey: string, contactKey: string) => {
    const params = new URLSearchParams({ case_id: caseId, report_key: reportKey })
    return fetchAPI<CellebriteRecord>(
      `/api/cellebrite/overview/contact/${encodeURIComponent(contactKey)}?${params}`
    )
  },
}

export const cellebriteFilesAPI = {
  list: (
    caseId: string,
    opts: ReportScopedParams &
      PagedParams & {
        category?: string | null
        parentLabel?: string | null
        sourceApp?: string | null
        devicePath?: string | null
        tag?: string | null
        entityId?: string | null
        search?: string | null
        onlyRelevant?: boolean
        captureAfter?: string | null
        captureBefore?: string | null
        hasGeotag?: boolean | null
      } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    if (opts.category) params.set("category", opts.category)
    if (opts.parentLabel) params.set("parent_label", opts.parentLabel)
    if (opts.sourceApp) params.set("source_app", opts.sourceApp)
    if (opts.devicePath) params.set("device_path", opts.devicePath)
    if (opts.tag) params.set("tag", opts.tag)
    if (opts.entityId) params.set("entity_id", opts.entityId)
    if (opts.search) params.set("search", opts.search)
    if (opts.onlyRelevant) params.set("only_relevant", "true")
    if (opts.captureAfter) params.set("capture_after", opts.captureAfter)
    if (opts.captureBefore) params.set("capture_before", opts.captureBefore)
    if (opts.hasGeotag !== undefined && opts.hasGeotag !== null) {
      params.set("has_geotag", String(opts.hasGeotag))
    }
    appendPaging(params, opts, { limit: 500, offset: 0 })
    return fetchAPI<FilesResponse>(`/api/cellebrite/files?${params}`)
  },

  tree: (
    caseId: string,
    opts: ReportScopedParams & { groupBy?: "category" | "parent" | "app" | "path" } = {}
  ) => {
    const params = baseCaseParams(caseId, opts.reportKeys)
    params.set("group_by", opts.groupBy ?? "category")
    return fetchAPI<FileTreeResponse>(`/api/cellebrite/files/tree?${params}`)
  },
}

export const evidenceCellebriteAPI = {
  checkFolder: (caseId: string, folderPath: string) => {
    const params = new URLSearchParams({ case_id: caseId, folder_path: folderPath })
    return fetchAPI<CellebriteRecord>(`/api/evidence/cellebrite/check?${params}`)
  },

  processFolder: (
    caseId: string,
    folderPath: string,
    opts: { force?: boolean; replaceExisting?: boolean } = {}
  ) =>
    fetchAPI<{
      success: boolean
      message: string
      task_id?: string | null
      job_id?: string | null
      job_ids?: string[] | null
    }>(
      "/api/evidence/cellebrite/process",
      {
        method: "POST",
        body: {
          case_id: caseId,
          folder_path: folderPath,
          force: opts.force,
          replace_existing: opts.replaceExisting,
        },
      }
    ),
}

export function normaliseTracks(data: EventTracksResponse): EventTrack[] {
  return data.tracks ?? []
}
