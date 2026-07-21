import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { evidenceAPI } from "../api"
import { useEvidenceStore } from "../evidence.store"
import { TextSearchPanel } from "./TextSearchPanel"

vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: (props: { open: boolean; initialPage?: number }) =>
    props.open ? <div data-testid="viewer">Page {props.initialPage}</div> : null,
}))

const hit = (id: string, snippet: string, page = 7) => ({
  id,
  start_char: 10,
  end_char: 16,
  snippet,
  highlight_start: 7,
  highlight_end: 13,
  page_number: page,
  location_label: `Page ${page}`,
})

describe("TextSearchPanel", () => {
  beforeEach(() => {
    useEvidenceStore.getState().resetForCase(crypto.randomUUID())
    vi.restoreAllMocks()
  })

  it("renders safe highlights, honest caps, coverage, and opens a mapped PDF page", async () => {
    vi.spyOn(evidenceAPI, "searchText").mockResolvedValue({
      query: "needle",
      total_matches: 4,
      total_documents: 1,
      case_documents: 3,
      searchable_documents: 2,
      document_limit: 25,
      document_offset: 0,
      returned_documents: 1,
      has_more_documents: false,
      documents: [
        {
          evidence_id: "evidence-1",
          document_name: "report.pdf",
          folder_path: "Root / Reports",
          total_matches: 4,
          shown_matches: 3,
          matches_truncated: true,
          matches: [
            hit("one", "Before needle after"),
            hit("two", "Before needle again"),
            hit("three", "Before needle lastly"),
          ],
        },
      ],
    })
    useEvidenceStore.getState().setTextSearchTerm("needle")
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <TextSearchPanel caseId="case-1" />
      </QueryClientProvider>
    )

    expect(await screen.findByText("4 matches across 1 document", {}, { timeout: 1500 })).toBeInTheDocument()
    expect(screen.getByText("Showing 3 of 4 matches")).toBeInTheDocument()
    expect(screen.getByText("Searchable text is available for 2 of 3 case documents.")).toBeInTheDocument()
    expect(document.querySelector("mark")?.textContent).toBe("needle")

    fireEvent.click(screen.getAllByText(/Before/)[0])
    await waitFor(() => expect(screen.getByTestId("viewer")).toHaveTextContent("Page 7"))
  })
})
