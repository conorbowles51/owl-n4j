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
    await screen.findByText(/original transaction before correction/)
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
it("follows the recorded correction without losing the original source link", async () => {
  const fetch = mount()
  await screen.findByText(/original transaction before correction/)
  fetch.mockResolvedValue(
    new Response(
      JSON.stringify({
        ...citation,
        transaction_id: "replacement",
        ref_id: "TX-NEW",
        superseded_by_id: null,
        ledger_status: "admitted",
      })
    )
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Open corrected transaction" })
  )
  expect(await screen.findByText("TX-NEW · source.pdf")).toBeInTheDocument()
  expect(
    fetch.mock.calls.some(([url]) =>
      String(url).includes("/ledger/replacement/source?case_id=case")
    )
  ).toBe(true)
  expect(screen.getByTestId("highlight-input")).toHaveTextContent(
    citation.evidence_file_id
  )
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

it("assesses only text selected from the resolved evidence file", async () => {
  const fetch = mount()
  await screen.findByRole("button", { name: "Assess an amount in source text" })
  fetch.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        case_id: "case",
        evidence_file_id: citation.evidence_file_id,
        content: "Amount 1234",
        content_sha256: "b".repeat(64),
        start_char: 0,
        end_char: 11,
        character_count: 11,
        has_more: false,
        offset_unit: "unicode_code_points",
      })
    )
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Assess an amount in source text" })
  )
  const source = await screen.findByLabelText("Source text")
  expect(fetch.mock.calls[1][0]).toContain(
    `/source-files/${citation.evidence_file_id}/text?case_id=case`
  )
  expect(
    screen.getByRole("button", { name: "Assess selected amount" })
  ).toBeDisabled()
  fireEvent.select(source, { target: { selectionStart: 7, selectionEnd: 11 } })
  fireEvent.change(screen.getByLabelText("Currency (ISO code)"), {
    target: { value: "USD" },
  })
  fetch.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        case_id: "case",
        evidence_file_id: citation.evidence_file_id,
        content_sha256: "b".repeat(64),
        start_char: 7,
        end_char: 11,
        applied: false,
        offset_unit: "unicode_code_points",
        currency_source: "caller_supplied",
        limitation: "Selected text only.",
        assessment: {
          raw: "1234",
          currency: "USD",
          origin: "unknown",
          suspicion: "decimal_point_absent",
          explanation: "Review the source.",
          proposals: [{ minor_units: "1234", basis: "Possible decimal" }],
        },
      })
    )
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Assess selected amount" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent("12.34 USD")
  expect(fetch.mock.calls[2][0]).toContain(
    `/source-files/${citation.evidence_file_id}/amount-assessment?case_id=case`
  )
  expect(JSON.parse(String(fetch.mock.calls[2][1]?.body)).expected_text).toBe(
    "1234"
  )
  expect(fetch).toHaveBeenCalledTimes(3)
  fireEvent.click(
    screen.getByRole("button", { name: "Close amount assessment" })
  )
  expect(screen.queryByRole("status")).toBeNull()
  expect(screen.getByRole("button", { name: "Open source file" })).toBeEnabled()
})

it("keeps original file access when extracted text is unavailable", async () => {
  const fetch = mount()
  await screen.findByRole("button", { name: "Assess an amount in source text" })
  fetch.mockResolvedValueOnce(
    new Response(
      JSON.stringify({ detail: "Source text not found in this case." }),
      { status: 404 }
    )
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Assess an amount in source text" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Source text not found"
  )
  expect(screen.getByRole("button", { name: "Open source file" })).toBeEnabled()
  expect(screen.queryByLabelText("Source text")).toBeNull()
})
