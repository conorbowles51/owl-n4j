import { createContext, useContext } from "react"
export const BatchReviewContext = createContext<{
  batchId?: string
  rowId?: string
  draftRevision?: string
  draft?: import("./statement-review-draft").StatementDraft
  save: (request: unknown) => Promise<unknown>
  saved: () => void
  nextProblem?: () => Promise<void>
  previousProblem?: () => Promise<void>
} | null>(null)
export const useBatchReview = () => useContext(BatchReviewContext)
