import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { CitationProvider } from "@/components/citations/citations"
import { ChatMessage } from "./ChatMessage"
import type { ChatMessageData } from "../types"

const FILE = "0b6c2a1e-7d4f-4c1a-9e2b-5f3a8c9d0e11"
const sent = vi.hoisted(() => ({ hrefs: [] as string[][] }))
vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<object>()),
  fetchAPI: vi.fn(async (_url: string, opts: { body: { hrefs: string[] } }) => {
    sent.hrefs.push(opts.body.hrefs)
    return { items: opts.body.hrefs.map((href) => ({ href, scheme: "doc", status: "ok", page: 4, page_given: true,
      legacy: false, evidence_file_id: FILE, filename: "statement.pdf" })) }
  }),
}))
vi.mock("@/lib/protected-file", () => ({
  openProtectedFile: vi.fn(),
  useProtectedObjectUrl: () => ({ objectUrl: "blob:source", loading: false, error: null }),
}))
vi.mock("@/components/ui/evidence-pdf-document", () => ({
  EvidencePdfDocument: ({ page }: { page: number }) => <p>Showing source page {page}</p>,
}))

describe("ChatMessage sources", () => {
  it("opens the cited document at its page, by its file id when the answer gave one", async () => {
    const message = {
      id: "m1",
      role: "assistant",
      content: "Answer",
      sources: [{ filename: "statement.pdf", page: 4, cite: `doc://${FILE}/4` }, { filename: "other.pdf" }],
    } as unknown as ChatMessageData

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <CitationProvider caseId="case-1">
            <ChatMessage message={message} />
          </CitationProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )
    fireEvent.click(screen.getByRole("button", { name: /2 sources/ }))
    fireEvent.click(screen.getByRole("button", { name: /statement\.pdf p\.4/ }))
    expect(await screen.findByText("Showing source page 4")).toBeVisible()
    // a source without a file id is cited by name with no page, never page 1
    expect(sent.hrefs.flat()).toContain("doc://other.pdf")
    expect(sent.hrefs.flat()).toContain(`doc://${FILE}/4`)
  })

  it("has no placeholder citation panel left to reach", () => {
    // The old CitationPanel only said a viewer 'will be integrated'; citations open the real document viewer.
    const modules = import.meta.glob("./CitationPanel.tsx")
    expect(Object.keys(modules)).toEqual([])
  })
})
