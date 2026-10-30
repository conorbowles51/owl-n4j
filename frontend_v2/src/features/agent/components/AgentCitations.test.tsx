import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { evidenceAPI } from "@/features/evidence/api"
import { AgentCitationProvider, AgentMarkdown, NO_CITATION_PAGE } from "./AgentCitations"

vi.mock("@/lib/protected-file", () => ({
  openProtectedFile: vi.fn(),
  useProtectedObjectUrl: () => ({ objectUrl: "blob:source", loading: false, error: null }),
}))
vi.mock("@/components/ui/evidence-pdf-document", () => ({
  EvidencePdfDocument: ({ page }: { page: number }) => <p>Showing source page {page}</p>,
}))

function answer(content: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AgentCitationProvider caseId="case-1">
          <AgentMarkdown content={content} />
        </AgentCitationProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(evidenceAPI, "findByFilename").mockResolvedValue({ found: true, evidence_id: "file-9" })
})

it("opens the viewer at the cited page when a doc:// link in an agent answer is clicked", async () => {
  answer("The deposit is on [March statement.pdf, p.4](doc://March%20statement.pdf/4).")
  fireEvent.click(screen.getByRole("button", { name: "March statement.pdf, p.4" }))
  expect(await screen.findByRole("heading", { name: "March statement.pdf" })).toBeVisible()
  expect(evidenceAPI.findByFilename).toHaveBeenCalledWith("March statement.pdf", "case-1")
  expect(await screen.findByText("Showing source page 4")).toBeVisible()
  expect(screen.queryByText(NO_CITATION_PAGE)).toBeNull()
})

it("opens a citation with no page at the start of the file and says no page was given", async () => {
  answer("See [March statement.pdf](doc://March%20statement.pdf).")
  fireEvent.click(screen.getByRole("button", { name: "March statement.pdf" }))
  expect(await screen.findByText(NO_CITATION_PAGE)).toBeVisible()
  expect(await screen.findByText("Showing source page 1")).toBeVisible()
})
