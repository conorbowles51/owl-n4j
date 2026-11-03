import type { TranscriptSummary } from '../transcripts.api'
export function canonicalName(info: TranscriptSummary): string {
  if (info.changed_since_processing) return 'Transcript changed since processing'
  if (info.review_state === 'ready') return 'Ready to process'
  if (info.review_state === 'processed') return info.reviewed ? 'Processed · Reviewed' : 'Processed · Transcript not reviewed'
  if (info.revision_id) return 'Awaiting transcript review'
  return 'Not transcribed'
}
