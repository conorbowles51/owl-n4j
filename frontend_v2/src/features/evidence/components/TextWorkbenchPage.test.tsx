import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { evidenceAPI } from "../api"
import { textWorkbenchAPI, type TextPages } from "../text-workbench.api"
import { TextWorkbenchPage } from "./TextWorkbenchPage"

vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: (url: string | null) => ({ objectUrl: url ? `blob:${url}` : null, loading: false, error: null }),
}))
vi.mock("@/features/phones/collect-targets", () => ({
  useCollectTargets: () => ({ targets: [{ kind: "finding", id: "f1", label: "A finding" }], note: null, loading: false, error: null }),
}))
const fetched = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: fetched,
}))

const OCR = { kind: "ocr", words: "Read from the page image by OCR software (Tesseract), not confirmed by a person", machine_read: true, model: null, confidence: 71.5, low_confidence: true }
const pages = (over: Partial<TextPages> = {}): TextPages => ({
  evidence_id: "file-1", case_id: "case-1", document_name: "statement.pdf", source_type: null, original_available: true,
  image_pages: 3, pages_in_step: true, text_version: "a".repeat(64), read_at: null, character_count: 40,
  text_absent: null, page_image_failure: null, page_count: 3, page_offset: 0, page_limit: 5, has_more: false,
  pages: [
    { page_number: 1, label: "Page 1", start_char: 0, end_char: 16, text: "Paid to ACME Ltd", reader: { ...OCR, kind: "text_layer", machine_read: false, words: "The PDF's own text layer", confidence: null, low_confidence: false }, text_missing: null },
    { page_number: 2, label: "Page 2", start_char: 18, end_char: 32, text: "Wire to Globex", reader: OCR, text_missing: null },
    { page_number: 3, label: "Page 3", start_char: null, end_char: null, text: "", reader: null, text_missing: "OCR ran on this page and found no text. It may be blank or hold only a picture." },
  ],
  ...over,
})

function show(address: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[address]}>
        <Routes><Route path="/cases/:id/evidence/:fileId/text" element={<TextWorkbenchPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("TextWorkbenchPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    fetched.mockReset()
    fetched.mockResolvedValue({})
    vi.spyOn(textWorkbenchAPI, "pages").mockResolvedValue(pages())
    vi.spyOn(textWorkbenchAPI, "positions").mockResolvedValue({ available: true, rects: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.05 }] })
  })

  it("shows the page image beside its text, names the reader, and turning the page moves both", async () => {
    show("/cases/case-1/evidence/file-1/text?page=2")
    expect(await screen.findByTestId("page-text")).toHaveTextContent("Wire to Globex")
    const reader = screen.getByTestId("text-reader")
    expect(reader).toHaveTextContent("Machine reading")
    expect(reader).toHaveTextContent("OCR software")
    expect(reader).toHaveTextContent("OCR confidence 72%")
    expect(reader).toHaveTextContent("Low confidence")
    expect(screen.getByAltText("Page 2 of statement.pdf")).toHaveAttribute("src", expect.stringContaining("/page/2/image"))
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }))
    expect(await screen.findByText("Paid to ACME Ltd")).toBeInTheDocument()
    expect(screen.getByAltText("Page 1 of statement.pdf")).toBeInTheDocument()
  })

  it("says why a page has no text, and why a document has none", async () => {
    const first = show("/cases/case-1/evidence/file-1/text?page=3")
    expect(await screen.findByTestId("text-missing")).toHaveTextContent("found no text")
    first.unmount()
    vi.spyOn(textWorkbenchAPI, "pages").mockResolvedValue(pages({ text_absent: "This file has not been processed yet, so Loupe holds no text for it.", pages: [] }))
    show("/cases/case-1/evidence/file-1/text")
    expect(await screen.findByTestId("text-absent")).toHaveTextContent("not been processed")
  })

  it("finds within the document, marks the match on the text and on the image, and goes to its page", async () => {
    vi.spyOn(evidenceAPI, "getTextMatches").mockResolvedValue({
      query: "Wire", evidence_id: "file-1", total_matches: 1, returned_matches: 1, offset: 0, limit: 200, has_more: false,
      matches: [{ id: "m", start_char: 18, end_char: 22, snippet: "Wire to", highlight_start: 0, highlight_end: 4, page_number: 2, location_label: "Page 2" }],
    })
    show("/cases/case-1/evidence/file-1/text?q=Wire")
    expect(await screen.findByText("Match 1 of 1")).toBeInTheDocument()
    await waitFor(() => expect(document.querySelector('mark[data-mark="current"]')).toHaveTextContent("Wire"))
    expect(screen.getByAltText("Page 2 of statement.pdf")).toBeInTheDocument()
    expect(await screen.findByTestId("page-highlight")).toHaveStyle({ left: "10%" })
  })

  it("says when a page has no positions for the words", async () => {
    vi.spyOn(textWorkbenchAPI, "positions").mockResolvedValue({ available: false, rects: [] })
    vi.spyOn(evidenceAPI, "getTextMatches").mockResolvedValue({ query: "Wire", evidence_id: "file-1", total_matches: 0, returned_matches: 0, offset: 0, limit: 200, has_more: false, matches: [] })
    show("/cases/case-1/evidence/file-1/text?q=Wire&page=2")
    expect(await screen.findByText(/cannot be marked on the image/)).toBeInTheDocument()
    expect(screen.getByText("No matches in this text.")).toBeInTheDocument()
  })

  it("adds a selection to a finding as a quote, names its reader and sends only the passage", async () => {
    fetched.mockResolvedValue({ added: 1, skipped: 0, added_link_ids: ["l1"], version: 2 })
    show("/cases/case-1/evidence/file-1/text?page=2")
    const text = await screen.findByTestId("page-text")
    const node = text.querySelector("span")!.firstChild!
    const range = document.createRange()
    range.setStart(node, 8)
    range.setEnd(node, 14)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    fireEvent.mouseUp(text)
    const bar = await screen.findByRole("group", { name: "Selected text" })
    expect(bar).toHaveTextContent("“Globex”")
    expect(bar).toHaveTextContent("Stays labelled: Read from the page image by OCR software")
    fireEvent.click(within(bar).getByRole("button", { name: "Add to…" }))
    expect(screen.queryByRole("button", { name: /Timeline/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Label/ })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole("option", { name: "A finding" }))
    await waitFor(() => expect(fetched).toHaveBeenCalled())
    const [url, options] = fetched.mock.calls[0]
    expect(url).toBe("/api/workspace/case-1/entries/f1/links:batch")
    expect(options.body.links[0]).toMatchObject({ target_type: "evidence_passage", target_id: `file-1:${"a".repeat(16)}:26:32`, source_anchor: {} })
  })

  it("refuses a selection longer than a quote may be, in words", async () => {
    const long = "x".repeat(6000)
    vi.spyOn(textWorkbenchAPI, "pages").mockResolvedValue(pages({ pages: [{ page_number: 1, label: "Page 1", start_char: 0, end_char: 6000, text: long, reader: OCR, text_missing: null }] }))
    show("/cases/case-1/evidence/file-1/text")
    const text = await screen.findByTestId("page-text")
    const range = document.createRange()
    range.selectNodeContents(text)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
    fireEvent.mouseUp(text)
    expect(await screen.findByRole("alert")).toHaveTextContent("at most 5,000 characters")
    expect(screen.queryByRole("button", { name: "Add to…" })).not.toBeInTheDocument()
  })

  it("opens a kept quote at its passage", async () => {
    vi.spyOn(textWorkbenchAPI, "passage").mockResolvedValue({ state: "unchanged", words: null, quote: "Wire", reader: OCR, taken_page: 2, page_number: 2, start_char: 18, end_char: 22 })
    show("/cases/case-1/evidence/file-1/text?passage=file-1:aaa:18:22")
    await waitFor(() => expect(document.querySelector('mark[data-mark="passage"]')).toHaveTextContent("Wire"))
    expect(screen.getByAltText("Page 2 of statement.pdf")).toBeInTheDocument()
  })

  it("says when the document was read again and keeps the quote as taken", async () => {
    vi.spyOn(textWorkbenchAPI, "passage").mockResolvedValue({ state: "not_found", words: "This document was read again after this quote was taken, on 3 November 2026. The quote keeps the words as taken. Those words are not in the new reading, so the page is the one the quote came from.", quote: "Wire", reader: OCR, taken_page: 2, page_number: null, start_char: null, end_char: null })
    show("/cases/case-1/evidence/file-1/text?passage=file-1:aaa:18:22")
    const kept = await screen.findByTestId("kept-passage")
    expect(kept).toHaveTextContent("read again")
    expect(kept).toHaveTextContent("Quote as taken from page 2: “Wire”")
    expect(kept).toHaveTextContent("OCR software")
    expect(await screen.findByAltText("Page 2 of statement.pdf")).toBeInTheDocument()
  })
})
