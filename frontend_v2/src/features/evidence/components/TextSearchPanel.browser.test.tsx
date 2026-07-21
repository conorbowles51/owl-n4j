import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { evidenceAPI } from "../api"
import { useEvidenceStore } from "../evidence.store"
import { TextSearchPanel } from "./TextSearchPanel"

vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: () => null,
}))

describe("evidence text search in Chromium", () => {
  beforeEach(() => {
    useEvidenceStore.getState().resetForCase(crypto.randomUUID())
    vi.restoreAllMocks()
  })

  it("groups exact results and exposes explicit counts", async () => {
    vi.spyOn(evidenceAPI, "searchText").mockResolvedValue({
      query: "AC-0199",
      total_matches: 1,
      total_documents: 1,
      case_documents: 1,
      searchable_documents: 1,
      document_limit: 25,
      document_offset: 0,
      returned_documents: 1,
      has_more_documents: false,
      documents: [{
        evidence_id: "evidence-browser-1",
        document_name: "accounts.pdf",
        folder_path: "Root / Banking",
        total_matches: 1,
        shown_matches: 1,
        matches_truncated: false,
        matches: [{
          id: "hit-browser-1",
          start_char: 12,
          end_char: 19,
          snippet: "Account AC-0199 belongs to the subject",
          highlight_start: 8,
          highlight_end: 15,
          page_number: 4,
          location_label: "Page 4",
        }],
      }],
    })
    useEvidenceStore.getState().setTextSearchTerm("AC-0199")

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TextSearchPanel caseId="case-browser" />
      </QueryClientProvider>
    )

    expect(await screen.findByText("1 match across 1 document")).toBeVisible()
    expect(screen.getByText("accounts.pdf")).toBeVisible()
    expect(screen.getByText("Showing 1 of 1 matches")).toBeVisible()
    expect(document.querySelector("mark")?.textContent).toBe("AC-0199")
  })
})
