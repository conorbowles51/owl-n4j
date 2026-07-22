import { fetchAPI } from "@/lib/api-client"
import type {
  AdvisorSuggestion,
  Artifact,
  BackgroundTask,
  ClassificationStats,
  DirectoryBrowseResponse,
  IngestPreview,
  ProcessorInfo,
  ScanStats,
  TriageCase,
  TriageFileListParams,
  TriageFileListResponse,
  TriageProfile,
  TriageStage,
  TriageTemplate,
} from "./triage.types"

function casePath(caseId: string) {
  return encodeURIComponent(caseId)
}

function appendParams(params: Record<string, unknown>) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      qs.set(key, String(value))
    }
  })
  const text = qs.toString()
  return text ? `?${text}` : ""
}

export const triageAPI = {
  browseDirectory: (path = "/") =>
    fetchAPI<DirectoryBrowseResponse>(
      `/api/triage/browse${appendParams({ path })}`
    ),

  createCase: (data: {
    name: string
    description?: string
    source_path: string
  }) =>
    fetchAPI<TriageCase>("/api/triage/cases", {
      method: "POST",
      body: { description: "", ...data },
    }),

  listCases: async () => {
    const response = await fetchAPI<{ cases: TriageCase[] }>("/api/triage/cases")
    return response.cases
  },

  getCase: (caseId: string) =>
    fetchAPI<TriageCase>(`/api/triage/cases/${casePath(caseId)}`),

  deleteCase: (caseId: string) =>
    fetchAPI<{ status: string }>(`/api/triage/cases/${casePath(caseId)}`, {
      method: "DELETE",
    }),

  startScan: (caseId: string, resume = false) =>
    fetchAPI<{ task_id: string; message: string }>(
      `/api/triage/cases/${casePath(caseId)}/scan`,
      { method: "POST", body: { resume } }
    ),

  getStats: (caseId: string) =>
    fetchAPI<ScanStats>(`/api/triage/cases/${casePath(caseId)}/stats`),

  getFiles: (caseId: string, params: TriageFileListParams = {}) =>
    fetchAPI<TriageFileListResponse>(
      `/api/triage/cases/${casePath(caseId)}/files${appendParams({ ...params })}`
    ),

  startClassification: (caseId: string) =>
    fetchAPI<{ task_id: string; message: string }>(
      `/api/triage/cases/${casePath(caseId)}/classify`,
      { method: "POST" }
    ),

  getClassification: (caseId: string) =>
    fetchAPI<ClassificationStats>(
      `/api/triage/cases/${casePath(caseId)}/classification`
    ),

  uploadHashSet: (caseId: string, data: { name: string; hashes: string[] }) =>
    fetchAPI<{ name: string; valid_hashes: number }>(
      `/api/triage/cases/${casePath(caseId)}/hash-sets`,
      { method: "POST", body: data }
    ),

  listHashSets: async () => {
    const response = await fetchAPI<{ hash_sets: Array<Record<string, unknown>> }>(
      "/api/triage/hash-sets"
    )
    return response.hash_sets
  },

  generateProfile: (caseId: string) =>
    fetchAPI<{ task_id: string; message: string }>(
      `/api/triage/cases/${casePath(caseId)}/profile`,
      { method: "POST" }
    ),

  getProfile: (caseId: string) =>
    fetchAPI<TriageProfile | { message: string }>(
      `/api/triage/cases/${casePath(caseId)}/profile`
    ),

  getTimeline: async (caseId: string) => {
    const response = await fetchAPI<{ timeline: Array<Record<string, unknown>> }>(
      `/api/triage/cases/${casePath(caseId)}/timeline`
    )
    return response.timeline
  },

  getArtifacts: async (caseId: string) => {
    const response = await fetchAPI<{ artifacts: Artifact[] }>(
      `/api/triage/cases/${casePath(caseId)}/artifacts`
    )
    return response.artifacts
  },

  getMismatches: async (caseId: string) => {
    const response = await fetchAPI<{ mismatches: Array<Record<string, unknown>> }>(
      `/api/triage/cases/${casePath(caseId)}/mismatches`
    )
    return response.mismatches
  },

  listProcessors: async () => {
    const response = await fetchAPI<{ processors: ProcessorInfo[] }>(
      "/api/triage/processors"
    )
    return response.processors
  },

  createStage: (
    caseId: string,
    data: {
      name: string
      processor_name: string
      config?: Record<string, unknown>
      file_filter?: Record<string, unknown>
    }
  ) =>
    fetchAPI<TriageStage>(`/api/triage/cases/${casePath(caseId)}/stages`, {
      method: "POST",
      body: { config: {}, file_filter: {}, ...data },
    }),

  executeStage: (caseId: string, stageId: string, maxWorkers = 4) =>
    fetchAPI<{ task_id: string; message: string }>(
      `/api/triage/cases/${casePath(caseId)}/stages/${encodeURIComponent(stageId)}/execute`,
      { method: "POST", body: { max_workers: maxWorkers } }
    ),

  getStageResults: async (caseId: string, stageId: string) => {
    const response = await fetchAPI<{ artifacts: Artifact[] }>(
      `/api/triage/cases/${casePath(caseId)}/stages/${encodeURIComponent(stageId)}/results`
    )
    return response.artifacts
  },

  getFileProvenance: (caseId: string, filePath: string) =>
    fetchAPI<Record<string, unknown>>(
      `/api/triage/cases/${casePath(caseId)}/files/${encodeURIComponent(filePath)}/provenance`
    ),

  getFileArtifacts: async (caseId: string, filePath: string) => {
    const response = await fetchAPI<{ artifacts: Artifact[] }>(
      `/api/triage/cases/${casePath(caseId)}/files/${encodeURIComponent(filePath)}/artifacts`
    )
    return response.artifacts
  },

  advisorChat: (
    caseId: string,
    data: { question: string }
  ) =>
    fetchAPI<{ answer?: string; suggestions?: AdvisorSuggestion[] }>(
      `/api/triage/cases/${casePath(caseId)}/advisor/chat`,
      { method: "POST", body: data }
    ),

  advisorSuggest: async (caseId: string) => {
    const response = await fetchAPI<{ suggestions: AdvisorSuggestion[] }>(
      `/api/triage/cases/${casePath(caseId)}/advisor/suggest`
    )
    return response.suggestions
  },

  listTemplates: async () => {
    const response = await fetchAPI<{ templates: TriageTemplate[] }>(
      "/api/triage/templates"
    )
    return response.templates
  },

  createTemplate: (
    caseId: string,
    data: { name: string; description?: string }
  ) =>
    fetchAPI<TriageTemplate>(
      `/api/triage/cases/${casePath(caseId)}/templates`,
      { method: "POST", body: { description: "", ...data } }
    ),

  applyTemplate: (caseId: string, templateId: string) =>
    fetchAPI<{ stages: TriageStage[]; message: string }>(
      `/api/triage/cases/${casePath(caseId)}/apply-template`,
      { method: "POST", body: { template_id: templateId } }
    ),

  deleteTemplate: (templateId: string) =>
    fetchAPI<{ status: string }>(
      `/api/triage/templates/${encodeURIComponent(templateId)}`,
      { method: "DELETE" }
    ),

  ingestPreview: (
    caseId: string,
    data: {
      target_case_id: string
      file_ids?: string[]
      include_artifacts?: boolean
      file_filter?: Record<string, unknown> | null
    }
  ) =>
    fetchAPI<IngestPreview>(
      `/api/triage/cases/${casePath(caseId)}/ingest-preview`,
      { method: "POST", body: data }
    ),

  ingest: (
    caseId: string,
    data: {
      target_case_id: string
      file_ids?: string[]
      include_artifacts?: boolean
      file_filter?: Record<string, unknown> | null
    }
  ) =>
    fetchAPI<{ task_id: string; message: string }>(
      `/api/triage/cases/${casePath(caseId)}/ingest`,
      { method: "POST", body: data }
    ),

  listTasks: async (caseId: string, limit = 25) => {
    const response = await fetchAPI<{ tasks: BackgroundTask[] }>(
      `/api/background-tasks${appendParams({ case_id: caseId, limit })}`
    )
    return response.tasks
  },
}
