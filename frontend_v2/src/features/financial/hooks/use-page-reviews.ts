import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

const pageReview = z.object({
  id: z.string(),
  page_number: z.number(),
  disposition: z.string(),
  label: z.string(),
  reason: z.string(),
  saved_by: z.string().nullable(),
  saved_at: z.string(),
  same_file_bytes: z.boolean(),
  origin: z.record(z.string(), z.unknown()).nullable(),
  undone_at: z.string().nullable(),
  undone_by: z.string().nullable(),
})
export type PageReview = z.infer<typeof pageReview>
const pageReviews = z.object({
  reviews: z.array(pageReview),
  history: z.array(pageReview),
})

export const pageReviewKey = (caseId: string, fileId: string) => [
  "statement-page-reviews",
  caseId,
  fileId,
]
export const pageReviewUrl = (fileId: string, caseId: string, suffix = "") =>
  `/api/financial/statement-import/${fileId}/page-reviews${suffix}?${new URLSearchParams({ case_id: caseId })}`
export const parsePageReviews = (value: unknown) => pageReviews.parse(value)

export function pagesReviewedOf(reviews: PageReview[], pages: number[]) {
  const reviewed = new Set(reviews.map((review) => review.page_number))
  return pages.filter((page) => reviewed.has(page)).length
}

/** Saved page reviews of one file. A failed read leaves the pages as they were, with the failure stated. */
export function usePageReviews(caseId: string, fileId: string) {
  const query = useQuery({
    queryKey: pageReviewKey(caseId, fileId),
    queryFn: async () =>
      parsePageReviews(await fetchAPI(pageReviewUrl(fileId, caseId))),
  })
  const reviews = query.data?.reviews
  const history = query.data?.history
  return useMemo(
    () => ({
      reviews: reviews ?? [],
      history: history ?? [],
      byPage: new Map((reviews ?? []).map((item) => [item.page_number, item])),
      failed: query.isError,
    }),
    [reviews, history, query.isError]
  )
}
