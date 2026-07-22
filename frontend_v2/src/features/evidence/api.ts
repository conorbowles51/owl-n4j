import { fetchAPI } from "@/lib/api-client"
import type {
  EvidenceFile,
  EvidenceSummary,
  VideoFrame,
  IngestionLog,
  WiretapCheckResult,
  LLMModel,
  AIModelPolicy,
  EvidenceDocumentMatchesResponse,
  EvidenceTextSearchResponse,
} from "@/types/evidence.types"

export interface UploadResponse {
  files?: EvidenceFile[]
  task_id?: string
  task_ids?: string[]
  job_ids?: string[]
  message?: string
}

const EVIDENCE_UPLOAD_TIMEOUT_MS = 60 * 60 * 1000

export interface EvidenceUploadOptions {
  isFolder?: boolean
  isArchive?: boolean
  replaceExisting?: boolean
  folderId?: string
}

export const evidenceAPI = {
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
    return fetchAPI<EvidenceTextSearchResponse>(`/api/evidence/text-search?${qs}`, {
      signal,
    })
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
  ) => {
    const options =
      typeof optionsOrIsFolder === "boolean"
        ? { isFolder: optionsOrIsFolder, folderId }
        : optionsOrIsFolder
    const isFolderUpload = options.isFolder || options.isArchive
    const formData = new FormData()
    formData.append("case_id", caseId)
    if (isFolderUpload) formData.append("is_folder", "true")
    if (options.isArchive) formData.append("is_archive", "true")
    if (options.replaceExisting) formData.append("replace_existing", "true")
    if (options.folderId) formData.append("folder_id", options.folderId)
    files.forEach((file) => {
      const multipartFilename =
        isFolderUpload && !options.isArchive
          ? file.webkitRelativePath || file.name
          : file.name
      formData.append("files", file, multipartFilename)
    })
    return fetchAPI<UploadResponse>("/api/evidence/upload", {
      method: "POST",
      body: formData,
      timeout: EVIDENCE_UPLOAD_TIMEOUT_MS,
    })
  },

  process: (caseId: string, fileIds: string[], profile?: string) =>
    fetchAPI<void>("/api/evidence/process", {
      method: "POST",
      body: { case_id: caseId, file_ids: fileIds, profile },
    }),

  processBackground: (
    caseId: string,
    fileIds: string[],
    profile?: string,
    maxWorkers = 4,
    imageProvider?: string
  ) =>
    fetchAPI<{ task_id?: string | null; job_ids?: string[] | null; message?: string }>(
      "/api/evidence/process/background",
      {
      method: "POST",
      body: {
        case_id: caseId,
        file_ids: fileIds,
        profile: profile || undefined,
        max_workers: maxWorkers,
        image_provider: imageProvider || undefined,
      },
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

  logs: async (caseId: string, limit = 50) => {
    const res = await fetchAPI<{ logs: IngestionLog[] }>(
      `/api/evidence/logs?case_id=${caseId}&limit=${limit}`
    )
    return res.logs
  },

  getFileUrl: (evidenceId: string) => `/api/evidence/${evidenceId}/file`,

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

  getVideoFrames: (
    evidenceId: string,
    interval = 30,
    maxFrames = 50
  ) =>
    fetchAPI<{ frames: VideoFrame[] }>(
      `/api/evidence/${evidenceId}/frames?interval=${interval}&max_frames=${maxFrames}`
    ),

  getVideoFrameUrl: (evidenceId: string, filename: string) =>
    `/api/evidence/${evidenceId}/frames/${encodeURIComponent(filename)}`,

  syncFilesystem: (caseId: string) =>
    fetchAPI<{ synced: number }>(`/api/evidence/sync-filesystem?case_id=${caseId}`, {
      method: "POST",
    }),

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
      body: { case_id: caseId, folder_paths: folderPaths, whisper_model: whisperModel },
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
  updatePolicy: (revision: number, configuration: AIModelPolicy["configuration"]) =>
    fetchAPI<AIModelPolicy>("/api/llm-config/policy", {
      method: "PUT",
      body: { revision, configuration },
    }),
}
