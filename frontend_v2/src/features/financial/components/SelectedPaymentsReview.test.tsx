import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { SelectedPaymentsReview } from "./SelectedPaymentsReview"
import { paymentFixture } from "../lib/payment-fixture.test-support"
const mocks = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock("@/lib/api-client", () => ({ fetchAPI: mocks.fetch }))
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({
    transactionId,
    onClose,
  }: {
    transactionId: string
    onClose: () => void
  }) => (
    <div>
      Source {transactionId}
      <button onClick={onClose}>Close source</button>
    </div>
  ),
}))
function source(id: string, status = "admitted") {
  return {
    case_id: "case",
    transaction_id: id,
    ref_id: `REF-${id}`,
    transaction: {
      ...paymentFixture,
      key: id,
      ref_id: `REF-${id}`,
      description: `Payment ${id}`,
      ledger_status: status,
      superseded_by_id: status === "superseded" ? "new" : null,
    },
    source_document_id: "document",
    evidence_file_id: "11111111-1111-4111-8111-111111111111",
    filename: `${id}.pdf`,
    sha256_at_ingestion: "a".repeat(64),
    recorded_digest_matches: true,
    file_bytes_verified: false,
    locator_state: "stored",
    locator: { kind: "page_only", page: 1 },
    ledger_status: status,
    superseded_by_id: status === "superseded" ? "new" : null,
    limitation: "Stored citation",
  }
}
beforeEach(() => {
  mocks.fetch
    .mockReset()
    .mockImplementation(async (path: string) =>
      source(path.split("/ledger/")[1].split("/")[0])
    )
})
function mount(initial = ["one", "old"]) {
  function Harness() {
    const [ids, setIds] = useState(initial)
    return (
      <>
        <p>IDs: {ids.join(",")}</p>
        <SelectedPaymentsReview
          caseId="case"
          ids={ids}
          onRemove={(id) =>
            setIds((previous) => previous.filter((value) => value !== id))
          }
          onClose={() => {}}
        />
      </>
    )
  }
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Harness />
    </QueryClientProvider>
  )
}
it("shows a corrected selected payment and removes only that ID without changing evidence", async () => {
  mocks.fetch.mockImplementation(async (path: string) =>
    path.includes("/old/") ? source("old", "superseded") : source("one")
  )
  mount()
  const row = (await screen.findByText("Payment old")).closest("li")!
  expect(within(row).getByRole("status")).toHaveTextContent(
    "Corrected since you selected it"
  )
  expect(within(row).getByText(/90,071,992,547,409.93 EUR/)).toBeInTheDocument()
  fireEvent.click(within(row).getByRole("button", { name: "Open transaction" }))
  await screen.findByText("Source old")
  fireEvent.click(screen.getByRole("button", { name: "Close source" }))
  await waitFor(() =>
    expect(
      screen.queryByText("Checking selected payments…")
    ).not.toBeInTheDocument()
  )
  fireEvent.click(
    within(screen.getByText("Payment old").closest("li")!).getByRole("button", {
      name: "Remove from selection",
    })
  )
  await screen.findByText("IDs: one")
  await screen.findByText("Payment one")
  expect(screen.queryByText("Payment old")).not.toBeInTheDocument()
  expect(mocks.fetch.mock.calls.every(([, options]) => !options.method)).toBe(
    true
  )
})
it("identifies an excluded payment separately from a loading failure", async () => {
  mocks.fetch.mockResolvedValue(source("one", "rejected"))
  mount(["one"])
  await screen.findByText(/This payment is no longer included/)
  expect(screen.getByRole("status")).toHaveTextContent(
    "This payment is no longer included"
  )
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})
it("retains every selected ID during a temporary failure and retries without treating it as excluded", async () => {
  mocks.fetch
    .mockRejectedValueOnce(Error("503"))
    .mockResolvedValue(source("one"))
  mount(["one"])
  await screen.findByRole("alert")
  expect(screen.getByText("IDs: one")).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Open transaction" })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Retry payment check" }))
  await screen.findByText("Payment one")
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})
it("hides mismatched case details and inconsistent correction status", async () => {
  mocks.fetch
    .mockResolvedValueOnce({ ...source("one"), case_id: "other" })
    .mockResolvedValue({ ...source("old"), superseded_by_id: "new" })
  mount()
  expect(await screen.findAllByRole("alert")).toHaveLength(2)
  expect(screen.queryByText("Payment one")).not.toBeInTheDocument()
  expect(screen.queryByText("Payment old")).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Open transaction" })
  ).not.toBeInTheDocument()
})
it("loads only the current twenty selected payments and returns to a valid page after removal", async () => {
  mount(Array.from({ length: 21 }, (_, i) => String(i)))
  await screen.findByText("Payment 19")
  expect(mocks.fetch).toHaveBeenCalledTimes(20)
  fireEvent.click(
    screen.getByRole("button", { name: "Next selected payments" })
  )
  await screen.findByText("Payment 20")
  expect(mocks.fetch).toHaveBeenCalledTimes(21)
  fireEvent.click(screen.getByRole("button", { name: "Remove from selection" }))
  await screen.findByText("Payment 0")
  expect(screen.queryByText("Payment 20")).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Next selected payments" })
  ).not.toBeInTheDocument()
})
