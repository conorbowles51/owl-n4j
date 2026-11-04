import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** The thread header's Attachments (N) and counts (03 section 6.7, MD-1). Synthetic values. */
const api = vi.hoisted(() => ({ getThreadAttachments: vi.fn() }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
import { ThreadAttachments } from "./ThreadAttachments"

function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ThreadAttachments caseId="c" extraction="e1" threadKey="t1" title="Synthetic thread" back="/cases/c/phones/e1/records/conversations?thread=t1&at=ev9" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("Thread attachments", () => {
  it("states the references and opens Media scoped to the thread with the way back", async () => {
    api.getThreadAttachments.mockResolvedValue({ thread_key: "t1", referenced: 14, files: 11, not_in_report: 3, in_folders_only: 0, not_in_production: 0, words: "14 attachments referenced, 3 not in the report" })
    show()
    const link = await screen.findByRole("link", { name: "Attachments (11)" })
    const url = new URL(link.getAttribute("href")!, "http://x")
    expect(url.pathname).toBe("/cases/c/phones/e1/records/media")
    expect(url.searchParams.get("thread")).toBe("t1")
    expect(url.searchParams.get("back")).toBe("/cases/c/phones/e1/records/conversations?thread=t1&at=ev9")
    expect(screen.getByTestId("thread-attachment-words")).toHaveTextContent("14 attachments referenced, 3 not in the report")
  })

  it("shows nothing for a thread with no attachments", async () => {
    api.getThreadAttachments.mockResolvedValue({ thread_key: "t1", referenced: 0, files: 0, not_in_report: 0, in_folders_only: 0, not_in_production: 0, words: "0 attachments referenced" })
    show()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText(/Attachments/)).toBeNull()
  })
})
