import { fetchAPI } from "@/lib/api-client"

/** An agent answer, or an answer in Chat. */
export type AnswerSource = "agent" | "chat"
export type AnswerRatingKind = "missed_something" | "not_relevant" | "too_thin"
export interface AnswerRating {
  id: string
  source: AnswerSource
  message_id: string
  kind: AnswerRatingKind
  label: string
  note: string
  record_ref: string | null
}

// Kept out of agent/api.ts: that module is in the first screen's bundle, and ratings load with the answer.
/** lx-agenttools D20: a person rates an answer (or withdraws the rating); the active ratings come back. */
export const answerRatingsAPI = {
  rate: (
    caseId: string,
    messageId: string,
    rating: { kind: AnswerRatingKind; note?: string; recordRef?: string; withdraw?: boolean; source?: AnswerSource },
  ) =>
    fetchAPI<{ ratings: AnswerRating[] }>(`/api/agent/messages/${encodeURIComponent(messageId)}/rating`, {
      method: "PUT",
      body: {
        case_id: caseId,
        kind: rating.kind,
        note: rating.note ?? "",
        record_ref: rating.recordRef?.trim() || null,
        withdraw: rating.withdraw ?? false,
        source: rating.source ?? "agent",
      },
    }),

  list: (messageId: string, source: AnswerSource = "agent") =>
    fetchAPI<{ ratings: AnswerRating[] }>(`/api/agent/messages/${encodeURIComponent(messageId)}/ratings?source=${source}`),
}
