import { fetchAPI } from '@/lib/api-client'
import type { TranscriptSegment } from '@/types/evidence.types'

export interface TranscriptSummary {
  revision_id?: string
  reviewed?: boolean
  review_required?: boolean
  review_state?: 'awaiting_review' | 'ready' | 'processed'
  changed_since_processing?: boolean
  published_revision_id?: string | null
}
export interface Transcript extends TranscriptSummary {
  evidence_status: string
  revision_id: string
  evidence_id: string
  case_id: string
  original_text: string
  original_segments: TranscriptSegment[]
  transcription: string
  segments: TranscriptSegment[]
  speakers: Record<string, string>
  speaker_merges: Record<string, string>
  speaker_entity_ids: Record<string, string>
  payload: Record<string, unknown>
}
export interface ProcessingSelection {
  case_id: string
  file_ids?: string[]
  folder_id?: string | null
  recursive?: boolean
  ready_audio_only?: boolean
  review_queue?: boolean
  reprocess_completed?: boolean
}
export interface PlannedFile {
  id: string
  name: string
  audio: boolean
  reviewed: boolean
  skipped: boolean
  reason: string | null
}
export interface ProcessingPlan {
  review_enabled?: boolean
  id: string
  case_id: string
  file_count: number
  eligible_count: number
  audio_count: number
  unreviewed_audio_count: number
  document_count: number
  skipped_count: number
  files: PlannedFile[]
  selection: ProcessingSelection
}
export type AudioMode = 'review_first' | 'direct'
export const transcriptsAPI = {
  capabilities: () => fetchAPI<{ enabled: boolean; configured: boolean; engine_compatible: boolean }>('/api/evidence/transcript-review/capabilities'),
  queue: (caseId: string, folderId: string | null, recursive: boolean, state = 'awaiting_review', cursor = 0) =>
    fetchAPI<{ counts: { ready: number; awaiting_review: number }; items: { id: string; name: string }[]; next_cursor: number | null }>(
      `/api/evidence/transcript-queue/list?${new URLSearchParams({ case_id: caseId, folder_id: folderId ?? 'root', recursive: String(recursive), state, cursor: String(cursor) })}`),
  get: (id: string) => fetchAPI<Transcript>(`/api/evidence/${id}/transcript`),
  revision: (id: string, revision: string) => fetchAPI<{ payload: Transcript['payload']; rendered: { text: string; segments: TranscriptSegment[] } }>(
    `/api/evidence/${id}/transcript/revisions/${revision}`),
  save: (id: string, revision: string, changes: Record<string, unknown>) =>
    fetchAPI<Transcript>(`/api/evidence/${id}/transcript`, { method: 'PATCH',
      body: { expected_revision_id: revision, ...changes } }),
  review: (id: string, revision: string, requestKey: string) =>
    fetchAPI<Transcript>(`/api/evidence/${id}/transcript/reviews`, { method: 'POST',
      body: { revision_id: revision, request_key: requestKey } }),
  plan: (selection: ProcessingSelection) => fetchAPI<ProcessingPlan>('/api/evidence/processing-plans',
    { method: 'POST', body: selection }),
  files: (planId: string, cursor = 0) => fetchAPI<{ items: PlannedFile[]; next_cursor: number | null }>(
    `/api/evidence/processing-plans/${planId}/files?cursor=${cursor}&limit=100`),
}
