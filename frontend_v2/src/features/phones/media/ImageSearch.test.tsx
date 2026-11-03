import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

/** 05 17.6: image search by description, indexed on this server with true counts. Synthetic data only. */
const api = vi.hoisted(() => ({
  describeImageIndex: vi.fn(),
  createImageIndex: vi.fn(),
  getImageIndexJobs: vi.fn(),
  cancelImageIndex: vi.fn(),
  searchImages: vi.fn(),
  mediaObjectUrl: vi.fn().mockRejectedValue(new Error("not in a browser")),
}))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
import { ImageSearch } from "./ImageSearch"
import { coverageWords, imageLeftOutWords, indexJob } from "./image-search-words"

const facts = (over: object = {}) => ({
  images: 12, eligible: 7, indexed: 0, indexed_contents: 0, waiting: 0,
  left_out: { not_in_population: 1, not_in_production: 1, empty_placeholder: 1, could_not_open: 2, could_not_open_by_reason: { heic: 1, not_image: 1 } },
  uncategorised_files: 1, model_installed: true, model_words: null, model: "siglip2-base-patch16-224", model_id: "google/siglip2-base-patch16-224@75de2d5", revision_short: "75de2d5",
  population_words: "Images sent or received in a message, in a camera or screenshot folder, or whose metadata names a camera are indexed.", ...over,
})
const job = (over: object) => ({ id: "j1", total: 7, done: 0, embedded: 0, reused: 0, failed: 0, failed_by_reason: {}, queued: 7, running: 0, cancelled: false, cancelled_count: 0, state: "running", created_at: "2026-11-03T08:00:00Z", first_started_at: null, last_finished_at: null, noun: "images", ...over })
const LABEL = "Machine-ranked by siglip2-base-patch16-224 75de2d5; a result points to an image, it does not describe it."
const found = {
  query: "a red square", label: LABEL, model: "siglip2-base-patch16-224", model_id: "m", revision_short: "75de2d5", provider_words: "Made on this server.",
  scored: 30, shown: 2, coverage: facts({ eligible: 0, indexed: 30 }), truncated_query: false, truncated_words: null,
  results: [
    { rank: 1, content_sha256: "a".repeat(64), copy_count: 2, phones: ["C1", "C2"], copies: [
      { file_uid: "f1", extraction_id: "e1", phone_label: "C1", filename: "red.png", category: "Image", message_count: 1 },
      { file_uid: "f2", extraction_id: "e2", phone_label: "C2", filename: "red-copy.png", category: "Image", message_count: 0 }] },
    { rank: 2, content_sha256: "b".repeat(64), copy_count: 1, phones: ["C1"], copies: [
      { file_uid: "f3", extraction_id: "e1", phone_label: "C1", filename: "blue.jpg", category: "Image", message_count: 0 }] },
  ],
}

function renderIt(onOpen = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ImageSearch caseId="c" blur onOpen={onOpen} />
    </QueryClientProvider>,
  )
  return onOpen
}

describe("Image search by description (05 17.6)", () => {
  it("states the true number it would index and what it leaves out, starts it, and counts it in the job tray", async () => {
    api.describeImageIndex.mockResolvedValue(facts())
    api.getImageIndexJobs.mockResolvedValueOnce({ case_id: "c", items: [] }).mockResolvedValue({ case_id: "c", items: [job({ done: 3, reused: 1, embedded: 2, running: 4, queued: 0, first_started_at: "2026-11-03T08:00:01Z", last_finished_at: "2026-11-03T08:00:30Z" })] })
    api.createImageIndex.mockResolvedValue(job({}))
    renderIt()
    const go = await screen.findByRole("button", { name: "Index this case's images for search (7 images)" })
    expect(screen.getByText("Left out of 12 images: 1 not sent or received, not from a camera or screenshot folder, 1 not in the production, 1 empty placeholders, 2 could not be opened (1 stored as HEIC, which this server cannot open, 1 not a picture).")).toBeInTheDocument()
    fireEvent.click(go)
    await waitFor(() => expect(api.createImageIndex).toHaveBeenCalledWith("c"))
    fireEvent.click(await screen.findByRole("button", { name: "Jobs (1 running)" }))
    const tray = await screen.findByRole("list", { name: "Jobs" })
    expect(within(tray).getByText("Indexing 7 images for search by description")).toBeInTheDocument()
    expect(within(tray).getByText(/^Indexed: 3 of 7 images, /)).toBeInTheDocument()
  })

  it("says the model is not installed and offers nothing to start", async () => {
    api.describeImageIndex.mockResolvedValue(facts({ model_installed: false, model_words: "The image search model is not installed on this server. Nothing was sent anywhere." }))
    api.getImageIndexJobs.mockResolvedValue({ case_id: "c", items: [] })
    renderIt()
    expect(await screen.findByText("The image search model is not installed on this server. Nothing was sent anywhere.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Index this case's images/ })).toBeNull()
  })

  it("finds images by description: ranked, labelled machine-ranked, each with its phones and messages, and opens a file", async () => {
    api.describeImageIndex.mockResolvedValue(facts({ eligible: 0, indexed: 30 }))
    api.getImageIndexJobs.mockResolvedValue({ case_id: "c", items: [] })
    api.searchImages.mockResolvedValue(found)
    const onOpen = renderIt()
    fireEvent.change(await screen.findByLabelText("Find images by description"), { target: { value: " a red square " } })
    fireEvent.click(screen.getByRole("button", { name: "Find" }))
    await waitFor(() => expect(api.searchImages).toHaveBeenCalledWith("c", "a red square", 24))
    expect(await screen.findByText(LABEL)).toBeInTheDocument()
    expect(screen.getByText('Showing the 2 highest ranked of 30 indexed images for "a red square".')).toBeInTheDocument()
    const list = screen.getByRole("list", { name: "Images found" })
    const items = within(list).getAllByRole("listitem").filter((li) => li.parentElement === list)
    expect(items).toHaveLength(2)
    expect(within(items[0]).getByLabelText("Rank 1")).toHaveTextContent("1")
    expect(within(items[0]).getByText("On C1, C2 (2 copies)")).toBeInTheDocument()
    expect(within(items[0]).getByText(/carried by 1 message/)).toBeInTheDocument()
    expect(within(items[0]).getByText(/carried by no message/)).toBeInTheDocument()
    expect(screen.queryByText(/score/i)).toBeNull() // the score is shown only as a rank
    fireEvent.click(within(items[0]).getByRole("button", { name: "C2: red-copy.png" }))
    expect(onOpen).toHaveBeenCalledWith("f2")
    fireEvent.click(screen.getByRole("button", { name: "Show 24 more" }))
    await waitFor(() => expect(api.searchImages).toHaveBeenLastCalledWith("c", "a red square", 48))
  })

  it("words the coverage and a finished job with failures", () => {
    expect(coverageWords(facts({ indexed: 4, eligible: 2, waiting: 1 }) as never)).toBe("4 images are indexed; 3 images are not indexed yet; 4 images cannot be indexed; 1 image is outside the search (not sent or received, not from a camera).")
    expect(imageLeftOutWords(facts({ left_out: { not_in_population: 0, not_in_production: 0, empty_placeholder: 0, could_not_open: 0, could_not_open_by_reason: {} } }) as never)).toBe("")
    const done = indexJob(job({ state: "done", done: 5, failed: 2, queued: 0, failed_by_reason: { heic: 1, unreadable: 1 } }) as never)
    expect(done.state).toBe("done")
    expect(done.title).toBe("Indexing 7 images for search by description: 2 could not be indexed (1 stored as HEIC, which this server cannot open, 1 damaged or in a format this server cannot open)")
    const stopped = indexJob(job({ state: "cancelled", cancelled: true, done: 2, cancelled_count: 5, queued: 0 }) as never)
    expect(stopped.state).toBe("failed")
    expect(stopped.title).toBe("Indexing 7 images for search by description: stopped by request after 2 of 7; 5 not started were removed; indexed images are kept")
  })
})
