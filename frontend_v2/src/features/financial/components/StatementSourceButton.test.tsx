import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { StatementSourceButton } from "./StatementSourceButton"
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: ({
    open,
    documentName,
  }: {
    open: boolean
    documentName: string
  }) => (open ? <p>Viewing {documentName}</p> : null),
}))
afterEach(() => vi.restoreAllMocks())
const answer = {
  case_id: "case",
  period_id: "period",
  source_document_id: "document",
  evidence_file_id: "cdd17bd7-1708-49c2-bc20-3e488e52379f",
  filename: "statement.pdf",
  recorded_digest_matches: true,
  file_bytes_verified: false,
  limitation: "Exact statement page is not established.",
}
function mount(data: unknown = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <StatementSourceButton
        caseId="case"
        periodId="period"
        sourceDocumentId="document"
      />
    </QueryClientProvider>
  )
  return fetch
}
it("resolves registered source only after clicking, then opens its file", async () => {
  const fetch = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect statement source" })
  )
  expect(
    await screen.findByText("Exact statement page is not established.")
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Open statement file" }))
  expect(screen.getByText("Viewing statement.pdf")).toBeVisible()
})
it.each([
  { case_id: "other" },
  { period_id: "other" },
  { source_document_id: "other" },
  { recorded_digest_matches: false },
])("refuses a mismatched citation %j", async (change) => {
  mount({ ...answer, ...change })
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect statement source" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Source unavailable"
  )
  expect(
    screen.queryByRole("button", { name: "Open statement file" })
  ).not.toBeInTheDocument()
})
