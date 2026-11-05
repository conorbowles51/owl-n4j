import { fetchAPI } from "@/lib/api-client"
import type { Case, CaseMetadataUpdate } from "@/types/case.types"
import type { CaseProcessingProfile } from "@/types/evidence.types"

export type CaseListViewMode = "my_cases" | "all_cases"

export type AddressLookupMode = "auto" | "flag"

export interface AddressLookupState {
  /** The mode in force: the case's own, or the system default when none is set. */
  mode: AddressLookupMode
  chosen: AddressLookupMode | null
  default_mode: AddressLookupMode
  words: string
  /** Addresses never looked up yet (null when the graph did not answer). */
  waiting: number | null
}

export const casesAPI = {
  list: (viewMode?: CaseListViewMode, includeArchived = false) => {
    const qs = new URLSearchParams()
    if (viewMode) qs.set("view_mode", viewMode)
    if (includeArchived) qs.set("include_archived", "true")
    const suffix = qs.toString() ? `?${qs}` : ""
    return fetchAPI<{ cases: Case[]; total: number }>(
      `/api/cases${suffix}`
    ).then((r) => r.cases)
  },

  get: (caseId: string) => fetchAPI<Case>(`/api/cases/${caseId}`),

  create: (data: { title: string; description?: string }) =>
    fetchAPI<Case>("/api/cases", { method: "POST", body: data }),

  update: (caseId: string, data: CaseMetadataUpdate) =>
    fetchAPI<Case>(`/api/cases/${caseId}`, { method: "PATCH", body: data }),

  archive: (caseId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}/archive`, { method: "PATCH" }),

  unarchive: (caseId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}/unarchive`, { method: "PATCH" }),

  getProcessingProfile: (caseId: string) =>
    fetchAPI<CaseProcessingProfile>(`/api/cases/${caseId}/processing-profile`),

  updateProcessingProfile: (
    caseId: string,
    data: {
      source_profile_name: string | null
      context_instructions: string | null
      mandatory_instructions: string[]
      special_entity_types: { name: string; description?: string | null }[]
    }
  ) =>
    fetchAPI<CaseProcessingProfile>(`/api/cases/${caseId}/processing-profile`, {
      method: "PUT",
      body: data,
    }),

  getAddressLookup: (caseId: string) =>
    fetchAPI<AddressLookupState>(`/api/cases/${caseId}/address-lookup`),

  setAddressLookup: (caseId: string, mode: AddressLookupMode | null) =>
    fetchAPI<AddressLookupState>(`/api/cases/${caseId}/address-lookup`, { method: "PUT", body: { mode } }),

  /** Moves the case to Deleted items (restorable for 30 days); the title must be typed exactly. */
  delete: ({ caseId, confirmTitle }: { caseId: string; confirmTitle: string }) =>
    fetchAPI<void>(
      `/api/cases/${caseId}?confirm_title=${encodeURIComponent(confirmTitle)}`,
      { method: "DELETE" }
    ),

  deletePreview: (caseId: string) =>
    fetchAPI<CaseDeletePreview>(`/api/cases/${caseId}/delete-preview`),

  listDeleted: () => fetchAPI<DeletedCasesResponse>("/api/cases/deleted"),

  restore: (caseId: string) =>
    fetchAPI<Case>(`/api/cases/${caseId}/restore`, { method: "POST" }),
}

/** Record counts a case holds, keyed by table (what deleting it takes out of view). */
export type CaseRecordCounts = Record<string, number | string>

export interface CaseDeletePreview {
  case_id: string
  title: string
  holds: CaseRecordCounts
  /** Days a deleted case stays restorable; null while Deleted items are switched off (the delete is immediate). */
  restorable_days: number | null
}

export interface DeletedPerson {
  id: string
  name: string
  email: string
}

export interface DeletedCase {
  id: string
  title: string
  deleted_at: string
  deleted_by: DeletedPerson | null
  owner: DeletedPerson | null
  purge_at: string
  days_left: number
  holds: CaseRecordCounts
}

export interface DeletedCasesResponse {
  /** Deleted items switched on (server setting, off by default): off, deletes are immediate and the list is empty. */
  enabled: boolean
  cases: DeletedCase[]
  retention_days: number | null
}

/** Plain words for the counted tables, in the order a person reads them: [key, one, more than one]. */
export const CASE_COUNT_LABELS: [string, string, string][] = [
  ["evidence_files", "evidence file", "evidence files"],
  ["financial_accounts", "account", "accounts"],
  ["financial_statement_periods", "statement period", "statement periods"],
  ["financial_transactions", "ledger row", "ledger rows"],
  ["adjudications", "review decision", "review decisions"],
  ["financial_judgements", "judgement call", "judgement calls"],
  ["phone_extractions", "phone report", "phone reports"],
  ["phone_comm_events", "phone message or call", "phone messages and calls"],
  ["workspace_entries", "note or workspace entry", "notes and workspace entries"],
  ["case_memberships", "member", "members"],
]

export function describeCaseCounts(holds: CaseRecordCounts): string[] {
  return CASE_COUNT_LABELS.filter(([key]) => typeof holds[key] === "number" && (holds[key] as number) > 0).map(
    ([key, one, many]) => {
      const count = holds[key] as number
      return `${count.toLocaleString()} ${count === 1 ? one : many}`
    }
  )
}
