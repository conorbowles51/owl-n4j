import { fetchAPI } from "@/lib/api-client"

export type WorkspaceAITargetType = "dossier" | "theory"
export type WorkspaceAIOutputType =
  | "statement_summary"
  | "statement_comparison"
  | "theory_analysis"
export type WorkspaceAIJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
export type WorkspaceAIReviewStatus =
  | "pending_review"
  | "accepted"
  | "rejected"

export interface WorkspaceAICitation {
  source_id: string
  evidence_file_id: string
  interview_id?: string | null
  filename: string
  source_anchor: Record<string, unknown>
  content_hash: string
  excerpt: string
  url: string
  retrieval_roles?: string[]
}

export interface WorkspaceAIClaim {
  text: string
  citation_ids: string[]
}

export interface WorkspaceAIContent {
  headline?: string
  claims?: WorkspaceAIClaim[]
  consistencies?: WorkspaceAIClaim[]
  contradictions?: WorkspaceAIClaim[]
  omissions?: WorkspaceAIClaim[]
  material_changes?: WorkspaceAIClaim[]
  supporting?: WorkspaceAIClaim[]
  contradicting?: WorkspaceAIClaim[]
  supporting_not_found_reason?: string | null
  contradicting_not_found_reason?: string | null
  limitations?: string[]
}

export interface WorkspaceAIOutput {
  id: string
  case_id: string
  target_type: WorkspaceAITargetType
  target_id: string
  output_type: WorkspaceAIOutputType
  version: number
  parent_output_id?: string | null
  job_status: WorkspaceAIJobStatus
  review_status: WorkspaceAIReviewStatus
  citation_status: "pending" | "valid" | "invalid"
  progress: number
  cancel_requested: boolean
  content: WorkspaceAIContent
  citations: WorkspaceAICitation[]
  source_set: WorkspaceAICitation[]
  proposed_actions: Array<Record<string, unknown>>
  accepted_targets: Array<Record<string, unknown>>
  model_metadata: Record<string, unknown>
  error_message?: string | null
  rejection_reason?: string | null
  mandate_version_id: string
  mandate_version_number?: number | null
  requested_by_user_id?: string | null
  requested_by_name?: string | null
  reviewed_by_user_id?: string | null
  reviewed_by_name?: string | null
  started_at?: string | null
  completed_at?: string | null
  reviewed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface WorkspaceAIOutputList {
  outputs: WorkspaceAIOutput[]
  total: number
  limit: number
  offset: number
}

const base = (caseId: string) =>
  `/api/workspace/${encodeURIComponent(caseId)}/ai-outputs`

export const workspaceAIAPI = {
  list: (
    caseId: string,
    targetType: WorkspaceAITargetType,
    targetId: string,
  ) => {
    const query = new URLSearchParams({
      target_type: targetType,
      target_id: targetId,
      limit: "100",
    })
    return fetchAPI<WorkspaceAIOutputList>(`${base(caseId)}?${query}`)
  },
  start: (
    caseId: string,
    input: {
      target_type: WorkspaceAITargetType
      target_id: string
      output_type: WorkspaceAIOutputType
      interview_ids?: string[]
    },
  ) =>
    fetchAPI<WorkspaceAIOutput>(base(caseId), {
      method: "POST",
      body: input,
    }),
  cancel: (caseId: string, outputId: string) =>
    fetchAPI<WorkspaceAIOutput>(`${base(caseId)}/${outputId}/cancel`, {
      method: "POST",
    }),
  retry: (caseId: string, outputId: string) =>
    fetchAPI<WorkspaceAIOutput>(`${base(caseId)}/${outputId}/retry`, {
      method: "POST",
    }),
  accept: (caseId: string, outputId: string) =>
    fetchAPI<WorkspaceAIOutput>(`${base(caseId)}/${outputId}/accept`, {
      method: "POST",
    }),
  reject: (caseId: string, outputId: string, reason?: string) =>
    fetchAPI<WorkspaceAIOutput>(`${base(caseId)}/${outputId}/reject`, {
      method: "POST",
      body: { reason: reason || undefined },
    }),
}
