import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateReviewForm } from "./CandidateReviewForm"
import { PdfCandidatesPanel } from "./PdfCandidatesPanel"

vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: ({
    sourceDocumentId,
  }: {
    sourceDocumentId: string
  }) => <p>Source file: {sourceDocumentId}</p>,
}))
afterEach(() => vi.restoreAllMocks())
const original = {
  cells: [{ column_index: 0, proposed_meaning: "amount", text: "1234" }],
}
const base = {
  candidate_id: "row-a",
  case_id: "case-a",
  original,
  status: "pending",
  reading: null,
  review_revision: "a".repeat(64),
  finalization_id: null,
  history: [],
  applied: false,
}
const accounts = {
  case_id: "case-a",
  has_more: false,
  items: [
    {
      id: "account-a",
      identifier: "1234",
      holder: "Test account",
      institution: null,
      currency: "GBP",
    },
  ],
}
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}
function mockServer(
  overrides: {
    review?: unknown
    writeStatus?: number
    accountCase?: string
  } = {}
) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url, options) => {
      const path = String(url)
      if (path.includes("ledger-accounts"))
        return json({ ...accounts, case_id: overrides.accountCase ?? "case-a" })
      if (path.includes("/review") && options?.method === "POST") {
        if (overrides.writeStatus)
          return json({ detail: "Changed; reload" }, overrides.writeStatus)
        const body = JSON.parse(String(options.body))
        return json({
          ...base,
          status: body.status,
          reading: body.reading,
          review_revision: "b".repeat(64),
        })
      }
      if (path.includes("/review")) return json(overrides.review ?? base)
      if (path.includes("candidate-mappings/mapping-a"))
        return json({
          id: "mapping-a",
          case_id: "case-a",
          evidence_file_id: "file-a",
          mapping_revision: "a".repeat(64),
          applied: false,
          original: {
            proposal: { case_id: "case-a", evidence_file_id: "file-a" },
          },
          candidates: [
            { id: "row-a", row_index: 0, status: "pending", original },
          ],
        })
      if (path.includes("candidate-mappings"))
        return json({
          case_id: "case-a",
          offset: 0,
          has_more: false,
          items: [
            {
              id: "mapping-a",
              evidence_file_id: "file-a",
              filename: "Synthetic.pdf",
              candidate_count: 1,
              created_at: "2026-09-07T03:00:00Z",
            },
          ],
        })
      throw new Error(`Unexpected request ${path}`)
    })
}
function mountForm() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const rendered = render(
    <QueryClientProvider client={client}>
      <CandidateReviewForm
        caseId="case-a"
        candidateId="row-a"
        mappingId="mapping-a"
        fileId="file-a"
        onClose={vi.fn()}
      />
    </QueryClientProvider>
  )
  return { ...rendered, invalidate }
}
async function fill() {
  await screen.findByRole("option", { name: /Test account/ })
  for (const [label, value] of [
    ["Currency", "GBP"],
    ["Reviewed amount", "2.00"],
    ["Account", "account-a"],
    ["Direction", "debit"],
    ["Booking date", "2026-02-01"],
    ["Reason for decision", "Checked original"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

it("does not query until PDF readings are opened and shows a saved batch", async () => {
  const fetch = mockServer()
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <PdfCandidatesPanel caseId="case-a" />
    </QueryClientProvider>
  )
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Open PDF readings" }))
  expect(await screen.findByText("Synthetic.pdf")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Open readings" }))
  expect(
    await screen.findByRole("button", { name: "Review source row 1" })
  ).toBeInTheDocument()
})

it("requires a case before loading saved readings", () => {
  const fetch = mockServer()
  render(<PdfCandidatesPanel caseId={undefined} />)
  expect(
    screen.getByText("Choose a case to review PDF readings.")
  ).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})

it("records an exact resolved reading with its reviewed revision", async () => {
  const fetch = mockServer()
  mountForm()
  await fill()
  fireEvent.click(
    screen.getByRole("button", { name: "Record resolved reading" })
  )
  expect(await screen.findByText(/Review recorded/)).toBeInTheDocument()
  const call = fetch.mock.calls.find(([, o]) => o?.method === "POST")!
  const body = JSON.parse(String(call[1]?.body))
  expect(body.reading.amount_minor).toBe("200")
  expect(body.reading.booking_date).toBe("2026-02-01")
  expect(body.reading.value_date).toBeNull()
  expect(body.expected_revision).toBe("a".repeat(64))
  expect(body).not.toHaveProperty("proof_class")
})

it("rejects without requiring guessed account date or amount", async () => {
  const fetch = mockServer()
  mountForm()
  fireEvent.change(await screen.findByLabelText("Reason for decision"), {
    target: { value: "Not a transaction" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Reject reading" }))
  await screen.findByText(/Review recorded/)
  const call = fetch.mock.calls.find(([, o]) => o?.method === "POST")!
  expect(JSON.parse(String(call[1]?.body)).reading).toBeNull()
})

it("will not resolve incomplete fields or a mismatched account currency", async () => {
  mockServer()
  mountForm()
  await fill()
  fireEvent.change(screen.getByLabelText("Currency"), {
    target: { value: "USD" },
  })
  expect(
    screen.getByRole("button", { name: "Record resolved reading" })
  ).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Currency"), {
    target: { value: "GBP" },
  })
  fireEvent.change(screen.getByLabelText("Booking date"), {
    target: { value: "" },
  })
  expect(
    screen.getByRole("button", { name: "Record resolved reading" })
  ).toBeDisabled()
})

it("blocks stale or uncertain retries until an explicit reload", async () => {
  const fetch = mockServer({ writeStatus: 409 })
  mountForm()
  await fill()
  fireEvent.click(
    screen.getByRole("button", { name: "Record resolved reading" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Reload to check its outcome"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Record resolved reading" })
  )
  expect(fetch.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    1
  )
  expect(
    screen.getByRole("button", { name: "Record resolved reading" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Reload review" }))
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  )
})

it("rejects a different case's review", async () => {
  mockServer({ review: { ...base, case_id: "other" } })
  mountForm()
  expect(await screen.findByRole("alert")).toHaveTextContent("different case")
  expect(
    screen.queryByRole("button", { name: "Reject reading" })
  ).not.toBeInTheDocument()
})

it("does not offer accounts from a different case", async () => {
  mockServer({ accountCase: "other" })
  mountForm()
  expect(await screen.findByRole("alert")).toHaveTextContent("different case")
  expect(
    screen.queryByRole("option", { name: /Test account/ })
  ).not.toBeInTheDocument()
})

it("preserves all existing date roles while editing a resolved reading", async () => {
  const reading = {
    account_id: "account-a",
    currency: "GBP",
    amount_minor: "900719925474099301",
    direction: "credit",
    booking_date: "2026-02-01",
    value_date: "2026-02-02",
    transaction_date: "2026-01-31",
    description: "Original description",
  }
  mockServer({ review: { ...base, status: "resolved", reading } })
  mountForm()
  expect(await screen.findByLabelText("Reviewed amount")).toHaveValue(
    "9007199254740993.01"
  )
  expect(screen.getByLabelText("Booking date")).toHaveValue("2026-02-01")
  expect(screen.getByLabelText("Value date")).toHaveValue("2026-02-02")
  expect(screen.getByLabelText("Transaction date")).toHaveValue("2026-01-31")
})

it("invalidates the original case after the form closes during a write", async () => {
  let finish!: (value: Response) => void
  const fetch = mockServer()
  const implementation = fetch.getMockImplementation()!
  fetch.mockImplementation((url, options) =>
    options?.method === "POST"
      ? new Promise<Response>((resolve) => {
          finish = resolve
        })
      : implementation(url, options)
  )
  const { unmount, invalidate } = mountForm()
  await fill()
  fireEvent.click(
    screen.getByRole("button", { name: "Record resolved reading" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Record resolved reading" })
  )
  await waitFor(() => expect(finish).toBeDefined())
  unmount()
  finish(json({ detail: "Uncertain response" }, 500))
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["financial-candidates", "case-a", "mapping"],
    })
  )
  expect(fetch.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    1
  )
})

it.each(["resolved", "rejected"])(
  "keeps finalized %s readings read-only with source assessment and history",
  async (status) => {
    const reading = {
      account_id: "account-a",
      currency: "GBP",
      amount_minor: "1234",
      direction: "debit",
      booking_date: "2026-02-01",
      value_date: null,
      transaction_date: null,
      description: "Synthetic",
    }
    const fetch = mockServer({
      review: {
        ...base,
        status,
        finalization_id: "seal-a",
        reading: status === "resolved" ? reading : null,
        history: [
          {
            id: "event-a",
            sequence: 1,
            status,
            reason: "Original review reason",
            reading: status === "resolved" ? reading : null,
            actor: { name: "Reviewer", email: "reviewer@example.test" },
            created_at: "2026-09-07T03:00:00Z",
          },
        ],
      },
    })
    mountForm()
    expect(await screen.findByText(/Finalized reading/)).toBeInTheDocument()
    expect(screen.getByLabelText("Reviewed amount")).toBeDisabled()
    expect(screen.getByLabelText("Reason for decision")).toBeDisabled()
    for (const name of [
      "Record resolved reading",
      "Reject reading",
      "Reopen for review",
      "Create provisional account",
    ])
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument()
    expect(screen.getByText("Original review reason")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Currency for source assessment"), {
      target: { value: "GBP" },
    })
    expect(
      screen.getByRole("button", { name: "Assess original amounts" })
    ).toBeEnabled()
    expect(
      fetch.mock.calls.filter(([, options]) => options?.method === "POST")
    ).toHaveLength(0)
  }
)

it("refuses a review response that omits its finalization state", async () => {
  mockServer({ review: { ...base, finalization_id: undefined } })
  mountForm()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Review could not be loaded"
  )
  expect(
    screen.queryByRole("button", { name: "Record resolved reading" })
  ).not.toBeInTheDocument()
})
