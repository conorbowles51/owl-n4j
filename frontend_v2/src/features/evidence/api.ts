import { fetchAPI } from "@/lib/api-client"
import { transcriptsAPI } from './transcripts.api'
import { uploadOrdinaryFiles } from "./resumable-upload"
import { uploadFolderOrArchive } from "./resumable-upload-groups"
import type { UploadProgress } from "./upload-progress"
import type {
  EvidenceFile,
  EvidenceFileRecord,
  EvidenceSummary,
  VideoFrame,
  IngestionLog,
  WiretapCheckResult,
  LLMModel,
  AIModelPolicy,
  EvidenceDocumentMatchesResponse,
  EvidenceTextSearchResponse,
  RouteCheckResponse,
  TranscriptSpeakerSettings,
} from "@/types/evidence.types"

export interface UploadResponse {
  files?: EvidenceFile[]
  file_ids?: string[]
  task_id?: string
  task_ids?: string[]
  job_ids?: string[]
  message?: string
}

export interface EvidenceUploadOptions {
  isFolder?: boolean
  isArchive?: boolean
  folderId?: string
  /** Hashing and sending progress for folder and archive uploads (07 J-1). */
  onProgress?: (progress: UploadProgress) => void
}

export const evidenceAPI = {
  createProcessingPlan: transcriptsAPI.plan,
  processingPlan: (planId: string) =>
    fetchAPI<{ id: string; execution?: { progress?: { sent: number; total: number } } | null }>(
      `/api/evidence/processing-plans/${planId}`, { read: true }),
  executeProcessingPlan: (planId: string, mode: import('./transcripts.api').AudioMode | undefined, requestKey: string) =>
    fetchAPI<{ job_ids: string[]; missing_on_disk?: number; message?: string }>(`/api/evidence/processing-plans/${planId}/executions`, {
      method: 'POST', body: { request_key: requestKey, audio_mode: mode },
    }),
  get: (evidenceId: string) =>
    fetchAPI<EvidenceFileRecord>(`/api/evidence/${evidenceId}`),

  list: async (caseId: string, status?: string) => {
    const qs = new URLSearchParams({ case_id: caseId })
    if (status) qs.set("status", status)
    const res = await fetchAPI<{ files: EvidenceFile[] }>(`/api/evidence?${qs}`)
    return res.files
  },

  searchText: (
    caseId: string,
    query: string,
    documentLimit = 25,
    documentOffset = 0,
    signal?: AbortSignal
  ) => {
    const qs = new URLSearchParams({
      case_id: caseId,
      q: query,
      document_limit: String(documentLimit),
      document_offset: String(documentOffset),
    })
    return fetchAPI<EvidenceTextSearchResponse>(
      `/api/evidence/text-search?${qs}`,
      {
        signal,
      }
    )
  },

  getTextMatches: (
    evidenceId: string,
    query: string,
    limit = 50,
    offset = 0,
    signal?: AbortSignal
  ) => {
    const qs = new URLSearchParams({
      q: query,
      limit: String(limit),
      offset: String(offset),
    })
    return fetchAPI<EvidenceDocumentMatchesResponse>(
      `/api/evidence/${evidenceId}/text-matches?${qs}`,
      { signal }
    )
  },

  upload: (
    caseId: string,
    files: File[],
    optionsOrIsFolder: EvidenceUploadOptions | boolean = {},
    folderId?: string
  ): Promise<UploadResponse> => {
    const options =
      typeof optionsOrIsFolder === "boolean"
        ? { isFolder: optionsOrIsFolder, folderId }
        : optionsOrIsFolder
    const isFolderUpload = options.isFolder || options.isArchive
    if (!isFolderUpload)
      return uploadOrdinaryFiles(caseId, files, options.folderId)
    return uploadFolderOrArchive(caseId, files, options)
  },

  process: (caseId: string, fileIds: string[], profile?: string) =>
    fetchAPI<void>("/api/evidence/process", {
      method: "POST",
      body: { case_id: caseId, file_ids: fileIds, profile },
    }),

  /**
   * Ask what these files are before asking for them to be processed.
   *
   * Takes the same two identifiers `processBackground` takes, so the answer
   * describes exactly the request that is about to be made. A check keyed on
   * anything else -- a folder, a selection, a page of results -- could be
   * answered for a different set of files than the ones eventually processed,
   * and this screen would have no way to notice the difference.
   */
  routeCheck: (caseId: string, fileIds: string[]) =>
    fetchAPI<RouteCheckResponse>("/api/evidence/route-check", {
      method: "POST",
      read: true,
      body: { case_id: caseId, file_ids: fileIds },
    }),

  // Offline source preparation only: this cannot request general document/AI processing.
  preparePdfReview: (caseId: string, fileId: string) =>
    fetchAPI("/api/evidence/process/background", {
      method: "POST",
      body: {
        case_id: caseId,
        file_ids: [fileId],
        preparation_mode: "pdf_review",
      },
      timeout: 120000,
    }),

  processBackground: (
    caseId: string,
    fileIds: string[],
    profile?: string,
    maxWorkers = 4,
    imageProvider?: string
  ) =>
    fetchAPI<{
      task_id?: string | null
      job_ids?: string[] | null
      missing_on_disk?: number
      message?: string
    }>("/api/evidence/process/background", {
      method: "POST",
      body: {
        case_id: caseId,
        file_ids: fileIds,
        profile: profile || undefined,
        max_workers: maxWorkers,
        image_provider: imageProvider || undefined,
      },
    }),

  releaseHold: (evidenceId: string, caseId: string) =>
    fetchAPI<EvidenceFile>(`/api/evidence/${evidenceId}/release-hold`, {
      method: "POST",
      body: { case_id: caseId },
    }),

  delete: (
    evidenceId: string,
    caseId: string,
    deleteExclusiveEntities = false
  ) =>
    fetchAPI<void>(
      `/api/evidence/${evidenceId}?case_id=${caseId}&delete_exclusive_entities=${deleteExclusiveEntities}`,
      { method: "DELETE" }
    ),

  listDeleted: (caseId: string) =>
    fetchAPI<DeletedEvidenceResponse>(`/api/evidence/deleted?case_id=${caseId}`),

  restore: (evidenceId: string, caseId: string) =>
    fetchAPI<{ evidence_id: string; filename: string; restored: boolean; merged_entities: string[] }>(
      `/api/evidence/${evidenceId}/restore?case_id=${caseId}`,
      { method: "POST" }
    ),

  /** Every deleted item of the case (files, folders, casework, links, ...): services/deleted_items.py. */
  listDeletedItems: (caseId: string) =>
    fetchAPI<DeletedItemsResponse>(`/api/cases/${caseId}/deleted-items`),

  restoreDeletedItem: (caseId: string, kind: string, id: string) =>
    fetchAPI<Record<string, unknown>>(
      `/api/cases/${caseId}/deleted-items/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/restore`,
      { method: "POST" }
    ),

  purgeDeletedItem: (caseId: string, kind: string, id: string) =>
    fetchAPI<PurgeResult>(
      `/api/cases/${caseId}/deleted-items/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/purge`,
      { method: "POST" }
    ),

  logs: async (caseId: string, limit = 50) => {
    const res = await fetchAPI<{ logs: IngestionLog[] }>(
      `/api/evidence/logs?case_id=${caseId}&limit=${limit}`
    )
    return res.logs
  },

  getFileUrl: (evidenceId: string) => `/api/evidence/${evidenceId}/file`,

  /**
   * One page of a PDF evidence file, rendered as a PNG at the given width
   * (backend default 1200; 100-3000 accepted). This is the image a stored
   * `page_rectangle` or `page_only` locator refers to — the page as
   * displayed, full page, so a fraction-of-page rectangle lands correctly.
   */
  getPageImageUrl: (evidenceId: string, page: number, width?: number) =>
    `/api/evidence/${evidenceId}/page/${page}/image${width ? `?width=${width}` : ""}`,

  updateTranscriptSpeakerSettings: (
    evidenceId: string,
    settings: TranscriptSpeakerSettings
  ) =>
    fetchAPI<TranscriptSpeakerSettings>(
      `/api/evidence/${evidenceId}/transcript-speakers`,
      {
        method: "PUT",
        body: settings,
      }
    ),

  getSummary: (filename: string, caseId: string) => {
    const qs = new URLSearchParams({ case_id: caseId })
    return fetchAPI<EvidenceSummary>(
      `/api/evidence/summary/${encodeURIComponent(filename)}?${qs}`
    )
  },

  findByFilename: (filename: string, caseId: string) => {
    const qs = new URLSearchParams({ case_id: caseId })
    return fetchAPI<{ found: boolean; evidence_id?: string }>(
      `/api/evidence/by-filename/${encodeURIComponent(filename)}?${qs}`
    )
  },

  getVideoFrames: (evidenceId: string, interval = 30, maxFrames = 50) =>
    fetchAPI<{ frames: VideoFrame[] }>(
      `/api/evidence/${evidenceId}/frames?interval=${interval}&max_frames=${maxFrames}`
    ),

  getVideoFrameUrl: (evidenceId: string, filename: string) =>
    `/api/evidence/${evidenceId}/frames/${encodeURIComponent(filename)}`,

  syncFilesystem: (caseId: string) =>
    fetchAPI<{ synced: number }>(
      `/api/evidence/sync-filesystem?case_id=${caseId}`,
      {
        method: "POST",
      }
    ),

  setRelevance: (evidenceIds: string[], isRelevant: boolean) =>
    fetchAPI<void>("/api/evidence/relevance", {
      method: "PUT",
      body: { evidence_ids: evidenceIds, is_relevant: isRelevant },
    }),

  checkWiretapFolder: (caseId: string, folderPath: string) => {
    const qs = new URLSearchParams({ case_id: caseId, folder_path: folderPath })
    return fetchAPI<WiretapCheckResult>(`/api/evidence/wiretap/check?${qs}`)
  },

  processWiretapFolders: (
    caseId: string,
    folderPaths: string[],
    whisperModel = "base"
  ) =>
    fetchAPI<{ task_id: string }>("/api/evidence/wiretap/process", {
      method: "POST",
      body: {
        case_id: caseId,
        folder_paths: folderPaths,
        whisper_model: whisperModel,
      },
    }),

  listFolderFiles: (caseId: string, folderPath: string) => {
    const qs = new URLSearchParams({ case_id: caseId, folder_path: folderPath })
    return fetchAPI<{ files: string[] }>(`/api/evidence/folder/files?${qs}`)
  },

  generateFolderProfile: (request: {
    case_id: string
    folder_path: string
    instructions: string
    profile_name?: string
  }) =>
    fetchAPI<Record<string, unknown>>("/api/evidence/folder/profile/generate", {
      method: "POST",
      body: request,
    }),

  testFolderProfile: (request: {
    case_id: string
    folder_path: string
    profile_config: Record<string, unknown>
  }) =>
    fetchAPI<Record<string, unknown>>("/api/evidence/folder/profile/test", {
      method: "POST",
      body: request,
    }),
}

export const llmConfigAPI = {
  getModels: (provider?: string) => {
    const qs = provider ? `?provider=${provider}` : ""
    return fetchAPI<{ models: LLMModel[] }>(`/api/llm-config/models${qs}`)
  },
  getPolicy: () => fetchAPI<AIModelPolicy>("/api/llm-config/policy"),
  updatePolicy: (
    revision: number,
    configuration: AIModelPolicy["configuration"]
  ) =>
    fetchAPI<AIModelPolicy>("/api/llm-config/policy", {
      method: "PUT",
      body: { revision, configuration },
    }),
}


export interface DeletedEvidenceFile {
  id: string
  filename: string
  size: number
  folder_id: string | null
  deleted_at: string
  purge_at: string
  days_left: number
  deleted_by: { id: string; name: string; email: string } | null
  holds: { graph_nodes: number; entities_only_in_this_file: number; text_chunks: number }
}

export interface DeletedEvidenceResponse {
  enabled: boolean
  files: DeletedEvidenceFile[]
  retention_days: number | null
  can_restore: boolean
}

export interface DeletedItem {
  kind: string
  kind_label: string
  id: string
  label: string | null
  deleted_at: string | null
  deleted_by: { id: string | null; name: string | null; email: string | null } | null
  detail: string | null
  purge_at: string | null
  days_left: number | null
  can_restore: boolean
  files?: number
  size?: number
}

export interface DeletedItemsResponse {
  enabled: boolean
  items: DeletedItem[]
  retention_days: number | null
  can_manage: boolean
}

export interface PurgeResult {
  kind: string
  id: string
  label: string | null
  purged: boolean
  counts: Record<string, number>
}
