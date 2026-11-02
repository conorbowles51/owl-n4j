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
vi.mock("@/features/phones/components/RecordPanel", () => ({
  PhoneRecordPanel: ({ recordUid, onClose }: { recordUid: string; onClose: () => void }) => (
    <section aria-label="Record behind this message">
      <p>Record {recordUid}</p>
      <button type="button" onClick={onClose}>Close record</button>
    </section>
  ),
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

it("opens the phone record's panel beside the answer when a rec:// link is clicked (S-7)", () => {
  const uid = "3af41de3-c6aa-4b1e-9d0e-2f4f0df3ffe5"
  answer(`She wrote it in [C3 WhatsApp message, Tue, Mar 14, 2023](rec://${uid}).`)
  fireEvent.click(screen.getByRole("button", { name: "C3 WhatsApp message, Tue, Mar 14, 2023" }))
  expect(screen.getByRole("region", { name: "Record behind this message" })).toHaveTextContent(`Record ${uid}`)
  fireEvent.click(screen.getByRole("button", { name: "Close record" }))
  expect(screen.queryByRole("region", { name: "Record behind this message" })).toBeNull()
})
