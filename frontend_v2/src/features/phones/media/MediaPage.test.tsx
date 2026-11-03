import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  getMediaIndex: vi.fn().mockResolvedValue({ total: 2, no_time_count: 1, missing: 1, by_category: { Image: 2 }, verification: { match: 1, missing: 1 } }),
  getMediaWindow: vi.fn().mockResolvedValue({ offset: 0, limit: 200, items: [
    { file_uid: "f1", extraction_id: "e1", phone_label: "C1", category: "Image", filename: "synthetic-a.jpg", size: 10, taken_or_sent: { instant: null, full: "Tuesday, March 14, 2023 3:07 PM", basis: "message_time" }, verification: "match", verification_words: "Intact: matches its stated hash", missing: false, deleted_state: null, is_carved: false, message_count: 1, thumbnail_url: null },
    { file_uid: "f2", extraction_id: "e1", phone_label: "C1", category: "Image", filename: "synthetic-gone.jpg", size: null, taken_or_sent: { instant: null, full: "No time recorded", basis: "none" }, verification: "missing", verification_words: "The report refers to a file that is not in the production.", missing: true, deleted_state: null, is_carved: false, message_count: 0, thumbnail_url: null },
  ] }),
  getMediaDetail: vi.fn().mockResolvedValue({ file_uid: "f1", extraction_id: "e1", category: "Image", local_path: "chats/synthetic-a.jpg", size: 10, hashes: { sha256: "ab" }, verification: "match", verification_words: "Intact: matches its stated hash", missing: false, missing_words: null, deleted_state: null, is_carved: false, message_count: 1, messages: [{ record_uid: "a1", message_record_uid: "m1", kind: "message", instant: "2023-03-14T19:07:00Z", mechanism: "attachment_extracted_path", mechanism_words: "the attachment's extracted path" }] }),
  mediaObjectUrl: vi.fn().mockRejectedValue(new Error("not in a browser")),
}))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
import MediaPage from "./MediaPage"

describe("Media (03 section 8)", () => {
  it("states the total, shows a missing file as the sentence, and opens a file with the messages that carried it (M-1, M-2, M-4)", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media"]}>
          <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText(/^2 files\./)).toBeInTheDocument()
    const grid = await screen.findByRole("list", { name: "Files" })
    expect(await within(grid).findByText("synthetic-gone.jpg")).toBeInTheDocument()
    expect(within(grid).getAllByText("The report refers to a file that is not in the production.").length).toBeGreaterThan(0)
    expect(within(grid).queryByRole("img", { name: "synthetic-gone.jpg" })).toBeNull()
    fireEvent.click(within(grid).getByText("synthetic-a.jpg"))
    const panel = await screen.findByRole("complementary", { name: "File" })
    expect(await within(panel).findByText("Carried by 1 message")).toBeInTheDocument()
    expect(within(panel).getByText(/found by the attachment's extracted path/)).toBeInTheDocument()
    expect(within(panel).getByRole("link", { name: /The message at/ })).toHaveAttribute("href", "/cases/c/records/m1")
  })
})
