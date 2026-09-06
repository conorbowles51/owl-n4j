import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: (props: {
    sourceDocumentId: string
    locatorPayload: unknown
  }) => <div data-testid="highlight-input">{JSON.stringify(props)}</div>,
}))
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: (props: {
    open: boolean
    documentUrl: string
    initialPage: number
  }) =>
    props.open ? (
      <div data-testid="file-viewer">{JSON.stringify(props)}</div>
    ) : null,
}))
afterEach(() => vi.restoreAllMocks())

const citation = {
  case_id: "case",
  transaction_id: "row",
  ref_id: "TX-OLD",
  source_document_id: "financial-document",
  evidence_file_id: "11111111-1111-4111-8111-111111111111",
  filename: "source.pdf",
  sha256_at_ingestion: "a".repeat(64),
  recorded_digest_matches: true,
  file_bytes_verified: false,
  locator_state: "stored",
  locator: { kind: "page_only", page: 3 },
  ledger_status: "superseded",
  superseded_by_id: "replacement",
  limitation: "Stored citation only.",
}
function mount(data: unknown = citation, status = 200) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(data), { status }))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LedgerSourceDialog caseId="case" transactionId="row" onClose={vi.fn()} />
    </QueryClientProvider>
  )
  return fetch
}
it("opens the evidence file and stored page, preserving the historical reading label", async () => {
  const fetch = mount()
  expect(
    await screen.findByText(/original reading that has been replaced/)
  ).toBeVisible()
  expect(screen.getByTestId("highlight-input")).toHaveTextContent(
    citation.evidence_file_id
  )
  expect(screen.getByTestId("highlight-input")).not.toHaveTextContent(
    "financial-document"
  )
  fireEvent.click(screen.getByRole("button", { name: "Open source file" }))
  expect(screen.getByTestId("file-viewer")).toHaveTextContent(
    `/api/evidence/${citation.evidence_file_id}/file`
  )
  expect(screen.getByTestId("file-viewer")).toHaveTextContent('"initialPage":3')
  expect(fetch.mock.calls[0][0]).toContain("/ledger/row/source?case_id=case")
})
it.each(["missing", "invalid"])(
  "explains %s locations and opens the file without a guessed page",
  async (state) => {
    mount({ ...citation, locator: null, locator_state: state })
    await screen.findByRole("button", { name: "Open source file" })
    expect(screen.queryByTestId("highlight-input")).toBeNull()
    expect(
      screen.getByText(
        state === "missing"
          ? /No location was stored/
          : /stored location could not be read/
      )
    ).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Open source file" }))
    expect(screen.getByTestId("file-viewer")).not.toHaveTextContent(
      "initialPage"
    )
  }
)
it.each([
  { case_id: "other" },
  { transaction_id: "other" },
  { recorded_digest_matches: false },
  { locator: { kind: "page_only", page: true } },
  { locator_state: "missing" },
])("refuses inconsistent citation metadata %j", async (change) => {
  mount({ ...citation, ...change })
  await screen.findByRole("alert")
  expect(screen.queryByRole("button", { name: "Open source file" })).toBeNull()
  expect(screen.queryByTestId("highlight-input")).toBeNull()
})
it("shows a digest refusal without fetching or opening evidence", async () => {
  const fetch = mount(
    { detail: "Recorded digest differs. Source navigation is unavailable." },
    409
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("digest differs")
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole("button", { name: "Open source file" })).toBeNull()
})
