import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ReviewSaveConflict } from "./ReviewSaveConflict"

afterEach(cleanup)
const saved = {
  review_revision: "rev2",
  saved_at: "2026-11-05T07:00:00+00:00",
  saved_by: { name: "A Colleague" },
  request: { holder: "Saved holder", rows: [] },
}
function mount(read: () => Promise<typeof saved | null>) {
  const onKeepSaved = vi.fn()
  const onReapply = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReviewSaveConflict
        queryKey={["conflict"]}
        read={read}
        local={{ holder: "My holder", rows: [] }}
        busy={false}
        onKeepSaved={onKeepSaved}
        onReapply={onReapply}
      />
    </QueryClientProvider>
  )
  return { onKeepSaved, onReapply }
}

it("shows saved beside local with who and when, and offers both choices", async () => {
  const { onKeepSaved, onReapply } = mount(async () => saved)
  expect(await screen.findByText(/Saved by A Colleague on/)).toBeVisible()
  expect(screen.getByRole("row", { name: "Account holder Saved holder My holder" })).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Keep the saved review" }))
  expect(onKeepSaved).toHaveBeenCalledWith(saved)
  fireEvent.click(screen.getByRole("button", { name: "Save my values over it" }))
  expect(onReapply).toHaveBeenCalledWith(saved)
})

it("keeps the local values and says so when the saved review cannot be read", async () => {
  mount(async () => {
    throw Error("offline")
  })
  expect(await screen.findByText(/could not be loaded\. offline/)).toBeVisible()
  expect(screen.getByText(/Your values are still here/)).toBeVisible()
  expect(screen.queryByRole("button", { name: "Keep the saved review" })).toBeNull()
})
