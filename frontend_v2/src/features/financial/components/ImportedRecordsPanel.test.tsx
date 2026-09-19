import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ImportedRecordsPanel } from "./ImportedRecordsPanel"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <p>Original PDF</p>,
}))
const record = {
  id: "1:0:1",
  source_document_id: "source",
  evidence_file_id: "file",
  filename: "Statement.pdf",
  currency: "EUR",
  page_number: 1,
  locator: null,
  original_text: "18 March Incoming payment",
  missing_fields: ["amount"],
  version: 0,
  fields: {
    id: "1:0:1",
    excluded: false,
    manual_page: null,
    date: "2023-03-18",
    date_unprinted: false,
    date_values: {},
    description: "Incoming payment",
    counterparty: "GlobalTech",
    amount_minor: "",
    direction: "credit",
    balance_minor: null,
    reason: "",
  },
}
const mount = (open = vi.fn()) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <ImportedRecordsPanel caseId="case" params={{}} onOpen={open} />
    </QueryClientProvider>
  )
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(fetchAPI).mockReset()
})
afterEach(cleanup)
it("retains missing values and an unfinished correction, then opens the saved transaction", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) =>
    options?.method === "POST"
      ? ({ transaction_id: "completed" } as never)
      : ({ records: [record], total: 1 } as never)
  )
  const open = vi.fn(),
    view = mount(open)
  await screen.findByText(/1 imported record has missing values/)
  fireEvent.click(screen.getByText(/1 imported record has/))
  fireEvent.click(screen.getByRole("button", { name: "Open record" }))
  expect(screen.getByLabelText("Amount")).toHaveValue("")
  fireEvent.change(screen.getByLabelText("Amount"), {
    target: { value: "125000.00" },
  })
  fireEvent.change(screen.getByLabelText("Reason for correction"), {
    target: { value: "Read against original" },
  })
  view.unmount()
  mount(open)
  await screen.findByText(/1 imported record has/)
  fireEvent.click(screen.getByText(/1 imported record has/))
  fireEvent.click(screen.getByRole("button", { name: "Open record" }))
  expect(screen.getByLabelText("Amount")).toHaveValue("125000.00")
  fireEvent.click(
    screen.getByRole("button", { name: "Save correction and open transaction" })
  )
  await waitFor(() => expect(open).toHaveBeenCalledWith("completed"))
  const call = vi
    .mocked(fetchAPI)
    .mock.calls.find(([, options]) => options?.method === "POST")
  expect(call?.[1]?.body).toMatchObject({
    version: 0,
    currency: "EUR",
    row: { amount_minor: "12500000", reason: "Read against original" },
  })
})
it("paginates retained records instead of silently truncating them", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    records: [record],
    total: 51,
  } as never)
  mount()
  await screen.findByText(/51 imported records/)
  fireEvent.click(screen.getByText(/51 imported records/))
  fireEvent.click(screen.getByRole("button", { name: "Next records" }))
  await waitFor(() =>
    expect(
      vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("offset=50"))
    ).toBe(true)
  )
})
