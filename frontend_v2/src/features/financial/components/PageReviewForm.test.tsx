import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

import { pagesReviewedOf, usePageReviews } from "../hooks/use-page-reviews"
import { PageReviewForm } from "./PageReviewForm"
const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

const review = (over = {}) => ({
  id: "r1",
  page_number: 3,
  disposition: "supporting_correspondence",
  label: "Supporting correspondence",
  reason: "Bank letter about fees",
  saved_by: "Investigator",
  saved_at: "2026-11-05T07:00:00+00:00",
  same_file_bytes: true,
  origin: null,
  undone_at: null,
  undone_by: null,
  ...over,
})

function Form({ canEdit }: { canEdit: boolean }) {
  const reviews = usePageReviews("case", "file")
  return <PageReviewForm caseId="case" fileId="file" page={3} reviews={reviews} canEdit={canEdit} />
}
const mount = (canEdit = true) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Form canEdit={canEdit} />
    </QueryClientProvider>
  )

beforeEach(() => fetchAPI.mockReset())
afterEach(cleanup)

it("saves a disposition with its reason and shows who saved it", async () => {
  fetchAPI.mockResolvedValueOnce({ reviews: [], history: [] })
  mount()
  await screen.findByText("No saved review of this page.")
  expect(screen.getByRole("button", { name: "Save review of page 3" })).toBeDisabled()
  fetchAPI.mockResolvedValueOnce({ reviews: [review()], history: [review()] })
  fireEvent.change(screen.getByLabelText("What page 3 is"), { target: { value: "supporting_correspondence" } })
  fireEvent.change(screen.getByLabelText("Why, for page 3"), { target: { value: "Bank letter about fees" } })
  fireEvent.click(screen.getByRole("button", { name: "Save review of page 3" }))
  await screen.findByText("Supporting correspondence: Bank letter about fees")
  expect(screen.getByText(/Saved by Investigator on/)).toBeVisible()
  expect(fetchAPI).toHaveBeenLastCalledWith(
    "/api/financial/statement-import/file/page-reviews/3?case_id=case",
    { method: "PUT", body: { disposition: "supporting_correspondence", reason: "Bank letter about fees", expected_review_id: null } }
  )
})

it("undoes a review and keeps it listed as earlier", async () => {
  fetchAPI.mockResolvedValueOnce({ reviews: [review()], history: [review()] })
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Undo this review" }))
  const undone = review({ undone_at: "2026-11-05T08:00:00+00:00", undone_by: "Investigator" })
  fetchAPI.mockResolvedValueOnce({ reviews: [], history: [undone] })
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenLastCalledWith(
      "/api/financial/statement-import/file/page-reviews/3/undo?case_id=case",
      { method: "POST", body: { expected_review_id: "r1" } }
    )
  )
})

it("labels a review a model saved, and a view-only person sees no controls", async () => {
  fetchAPI.mockResolvedValueOnce({
    reviews: [review({ origin: { kind: "model", model: "TestModel" } })],
    history: [],
  })
  mount(false)
  expect(await screen.findByText(/Read by TestModel · not confirmed/)).toBeVisible()
  expect(screen.queryByRole("button", { name: /Undo|Save/ })).toBeNull()
})

it("counts only flagged pages as reviewed", () => {
  expect(pagesReviewedOf([review(), review({ page_number: 9 })] as never, [3, 4])).toBe(1)
})
