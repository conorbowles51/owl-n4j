import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AssignedReviewsFeed } from "./ContinueReading"

const getWork = vi.hoisted(() => vi.fn())
vi.mock("./review-share", async (original) => ({
  ...(await original<object>()),
  getContinueWork: getWork,
}))
function show() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <AssignedReviewsFeed caseId="case-1" />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
describe("Workspace assigned reviews", () => {
  beforeEach(() => getWork.mockReset())
  it("preserves assigned review destinations without requesting browser reading history", async () => {
    getWork.mockResolvedValue({
      assigned: [
        {
          task_id: "review-1",
          title: "Review the harbour calls",
          kind: "threads",
          open: 3,
          total: 4,
          phones: ["phone-1"],
          items: [
            {
              thread_key: "thread-1",
              extraction_id: "phone-1",
              title: "Harbour calls",
              position: { event_uid: "message-3" },
            },
          ],
          next: [],
        },
      ],
      reading: [{ thread_key: "casual", title: "Casual reading" }],
    })
    show()
    expect(
      await screen.findByRole("link", { name: /Review the harbour calls/ })
    ).toHaveAttribute(
      "href",
      "/cases/case-1/phones/phone-1/records/conversations?thread=thread-1&at=message-3"
    )
    expect(getWork).toHaveBeenCalledWith("case-1", [])
    expect(screen.queryByText("Casual reading")).toBeNull()
  })
  it("recovers an assigned-review loading error", async () => {
    getWork
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ assigned: [], reading: [] })
    show()
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry reviews" })
    )
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull())
    expect(getWork).toHaveBeenCalledTimes(2)
  })
})
