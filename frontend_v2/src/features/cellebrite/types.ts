export type CellebriteRecord = Record<string, unknown>

export type CellebriteTabKey =
  | "overview"
  | "comms"
  | "unified"
  | "communications"
  | "locations"
  | "events"
  | "files"
  | "graph"
  | "timeline"

export type CommsType = "message" | "call" | "email"
export type ThreadType = "chat" | "calls" | "emails" | string
export type ParticipantMode = "any" | "from" | "to"

export interface PhoneReport extends CellebriteRecord {
  report_key: string
  display_index?: number | null
  device_model?: string | null
  device_name?: string | null
  device_name_override?: string | null
  phone_owner_name?: string | null
  owner_name?: string | null
  phone_number?: string | null
  imei?: string | null
  evidence_number?: string | null
  extraction_date?: string | null
  source_path?: string | null
  stats?: CellebriteRecord | null
}

export interface PhoneReportsResponse {
  reports: PhoneReport[]
}

export interface DeleteReportResponse extends CellebriteRecord {
  status?: string
  deleted_nodes?: number
  deleted_phone_report?: boolean
  deleted_evidence_records?: number
}

export interface TimelineItem extends CellebriteRecord {
  key?: string
  node_key?: string
  timestamp?: string | null
  event_type?: string | null
  type?: string | null
  label?: string | null
  summary?: string | null
  source_app?: string | null
  report_key?: string | null
  device_report_key?: string | null
}

export interface TimelineResponse extends CellebriteRecord {
  events?: TimelineItem[]
  items?: TimelineItem[]
  total?: number
  limit?: number
  offset?: number
}

export interface GraphNode extends CellebriteRecord {
  id?: string
  key?: string
  label?: string
  name?: string
  type?: string
  report_key?: string | null
}

export interface GraphLink extends CellebriteRecord {
  source?: string | GraphNode
  target?: string | GraphNode
  type?: string
  relationship?: string
  weight?: number
}

export interface CrossPhoneGraphResponse extends CellebriteRecord {
  nodes?: GraphNode[]
  links?: GraphLink[]
  edges?: GraphLink[]
  shared_contacts?: CellebriteRecord[]
}

export interface CommunicationNetworkResponse extends CellebriteRecord {
  persons?: CellebriteRecord[]
  contacts?: CellebriteRecord[]
  shared_contacts?: CellebriteRecord[]
  edges?: GraphLink[]
  links?: GraphLink[]
}

export interface CommsEntity extends CellebriteRecord {
  key?: string
  name?: string
  identifier?: string
  phone?: string
  report_keys?: string[]
  message_count?: number
  call_count?: number
  email_count?: number
}

export interface CommsSourceApp extends CellebriteRecord {
  app?: string
  source_app?: string
  name?: string
  count?: number
  thread_type?: string
}

export interface CommsParty extends CellebriteRecord {
  key?: string
  name?: string
  identifier?: string
  phone?: string
}

export interface CommsThread extends CellebriteRecord {
  thread_id: string
  thread_type: ThreadType
  name?: string | null
  source_app?: string | null
  last_activity?: string | null
  participants?: CommsParty[]
  item_count?: number
  message_count?: number
  report_key?: string | null
  device_report_key?: string | null
}

export interface CommsThreadsResponse extends CellebriteRecord {
  threads: CommsThread[]
  total?: number
  limit?: number
  offset?: number
}

export interface CommsItem extends TimelineItem {
  message_id?: string
  thread_id?: string
  thread_type?: ThreadType
  body?: string | null
  subject?: string | null
  direction?: string | null
  sender?: CommsParty | null
  recipients?: CommsParty[]
  counterpart?: CommsParty | null
  attachments?: Attachment[]
  attachment_file_ids?: string[]
}

export interface ThreadDetailResponse extends CellebriteRecord {
  thread?: CommsThread
  items?: CommsItem[]
  messages?: CommsItem[]
  total?: number
  limit?: number
  offset?: number
  anchor_key?: string | null
  anchor_found?: boolean
  anchor_index?: number | null
}

export interface CommsBetweenResponse extends CellebriteRecord {
  items: CommsItem[]
  total?: number
  limit?: number
  offset?: number
  next_cursor?: string | null
  cursor?: string | null
}

export interface ContactFeedResponse extends CommsBetweenResponse {
  contact?:
    | (CommsParty & {
        phone_numbers?: string[]
        is_phone_owner?: boolean
        all_identifiers?: string[]
      })
    | null
}

export interface CommsEnvelopeResponse extends CellebriteRecord {
  total?: number
  type_counts?: Record<string, number>
  min_date?: string | null
  max_date?: string | null
  histogram?: { date: string; count: number }[]
}

export interface SearchMessagesResponse extends CellebriteRecord {
  query?: string
  thread_ids?: string[]
  matches?: CommsItem[]
  total?: number
}

export interface Attachment extends CellebriteRecord {
  file_id?: string
  evidence_id?: string
  filename?: string
  category?: string
  mime_type?: string
  url?: string
}

export interface EventTypeCount extends CellebriteRecord {
  event_type?: string
  type?: string
  count?: number
}

export interface EventsResponse extends CellebriteRecord {
  events: TimelineItem[]
  total?: number
  limit?: number
  offset?: number
}

export interface LocationTile extends CellebriteRecord {
  tile_id?: string
  cell_x?: number
  cell_y?: number
  cell_deg?: number
  count?: number
  top_apps?: string[]
  latitude?: number
  longitude?: number
  lat?: number
  lng?: number
  lon?: number
}

export interface LocationTilesResponse extends CellebriteRecord {
  zoom?: number
  cell_deg?: number
  tiles: LocationTile[]
  total?: number
}

export interface LocationSuggestionValue extends CellebriteRecord {
  value: string
  count: number
}

export interface LocationSuggestionValuesResponse extends CellebriteRecord {
  location_type?: LocationSuggestionValue[]
  source_app?: LocationSuggestionValue[]
  country?: LocationSuggestionValue[]
  admin1?: LocationSuggestionValue[]
  place_name?: LocationSuggestionValue[]
}

export interface TrackPoint extends CellebriteRecord {
  latitude?: number
  longitude?: number
  lat?: number
  lng?: number
  timestamp?: string | null
}

export interface EventTrack extends CellebriteRecord {
  report_key?: string
  points?: TrackPoint[]
  coordinates?: TrackPoint[]
}

export interface EventTracksResponse extends CellebriteRecord {
  tracks: EventTrack[]
}

export interface LocationsInTileResponse extends CellebriteRecord {
  items?: TimelineItem[]
  locations?: TimelineItem[]
  rows?: TimelineItem[]
  per_phone?: LocationTilePhoneBreakdown[]
  total?: number
  truncated?: boolean
}

export interface LocationTilePhoneBreakdown extends CellebriteRecord {
  device_report_key?: string | null
  count: number
  first_seen?: string | null
  last_seen?: string | null
  apps?: Array<{ app: string; count: number }>
}

export interface LocationVisitor extends CellebriteRecord {
  device_report_key: string
  visit_count: number
  first_seen?: string | null
  last_seen?: string | null
  sample_keys?: string[]
}

export interface LocationVisitorsResponse extends CellebriteRecord {
  visitors: LocationVisitor[]
  radius_m?: number
  center?: { lat: number; lon: number }
}

export interface EventRelatedResponse extends CellebriteRecord {
  anchor?: TimelineItem
  thread?: CommsItem[]
  around?: CommsItem[]
}

export interface UnifiedContact extends CellebriteRecord {
  canonical_phone?: string | null
  phone?: string | null
  display_name?: string | null
  name?: string | null
  aliases?: string[]
  entity_keys?: string[]
  participant_keys?: string[]
  report_keys?: string[]
  message_count?: number
  call_count?: number
  email_count?: number
}

export interface UnifiedContactsResponse extends CellebriteRecord {
  contacts?: UnifiedContact[]
  rows?: UnifiedContact[]
  total?: number
  limit?: number
  offset?: number
}

export type OverviewKind =
  | "contacts"
  | "calls"
  | "messages"
  | "locations"
  | "emails"

export interface OverviewResponse extends CellebriteRecord {
  rows?: CellebriteRecord[]
  contacts?: CellebriteRecord[]
  calls?: CellebriteRecord[]
  messages?: CellebriteRecord[]
  locations?: CellebriteRecord[]
  emails?: CellebriteRecord[]
  total?: number
  limit?: number
  offset?: number
}

export interface FilesResponse extends CellebriteRecord {
  files: CellebriteRecord[]
  total?: number
}

export interface FileTreeNode extends CellebriteRecord {
  label: string
  count: number
  value?: string
  children?: FileTreeNode[]
}

export interface FileTreeResponse extends CellebriteRecord {
  group_by?: string
  root: FileTreeNode
}

export interface IntersectionRunResponse extends CellebriteRecord {
  methods?: string[]
  results?: CellebriteRecord[]
  intersections?: CellebriteRecord[]
}

export interface ReportScopedParams {
  reportKeys?: string[] | null
}

export interface PagedParams {
  limit?: number
  offset?: number
}

export interface DateRangeParams {
  startDate?: string | null
  endDate?: string | null
}

export interface CommsFilterParams
  extends ReportScopedParams, DateRangeParams, PagedParams {
  fromKeys?: string[] | null
  toKeys?: string[] | null
  participantKeys?: string[] | null
  threadTypes?: string[] | null
  sourceApps?: string[] | null
  types?: CommsType[] | null
  search?: string | null
  sort?: "asc" | "desc"
  cursor?: string | null
}

export interface RailSelection {
  id: string
  kind:
    | "thread"
    | "event"
    | "tile"
    | "contact"
    | "contact_unified"
    | "file"
    | "message"
    | "report"
  title: string
  payload: CellebriteRecord
}
