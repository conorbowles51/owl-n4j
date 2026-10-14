import { createContext, useContext } from "react"
export const BatchReviewContext = createContext<{
  readOnly?: boolean
  batchId?: string
  rowId?: string
  field?: "holder" | "account_number" | "period" | "currency" | "institution"
  /** From the queue: proposed values for missing details (value, source, certainty). */
  proposals?: Record<string, { value: string; label: string; confirmed?: boolean }>
  /** From the queue: blockers that remain after the proposed fix (empty: the fix makes it ready). */
  remaining?: string[]
  draftRevision?: string
  draft?: import("./statement-review-draft").StatementDraft
  save: (request: unknown) => Promise<unknown>
  confirm?: (request: unknown) => Promise<unknown>
  saved: () => void
  nextProblem?: () => Promise<void>
  previousProblem?: () => Promise<void>
  beforeNavigate?: { current: (() => Promise<unknown>) | null }
} | null>(null)
export const useBatchReview = () => useContext(BatchReviewContext)
