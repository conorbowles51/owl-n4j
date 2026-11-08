import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { FinancialAccessContext } from "../hooks/use-financial-access"
import { ReadingCheckContext, showReadingRow } from "../hooks/reading-check-context"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import { payerPayeeQuestion } from "../lib/payment-naming"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: (url: string | null) => ({ objectUrl: url ? `blob:${url}` : null, loading: false, error: null }),
}))
vi.mock("@/components/ui/document-viewer", () => ({ DocumentViewer: () => null }))
vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: (pick: (state: { user: { name: string; username: string } }) => unknown) =>
    pick({ user: { name: "Alex Rivera", username: "alex" } }),
}))

const origin = { kind: "model" as const, model: "Claude", for: { name: "Neil" }, at: "2026-10-28T10:00:00+00:00", citation: { page: 4, file: "s.pdf" } }
const KEY = ["financial-ledger", "case", null]

function reading(): LedgerTransaction {
  return {
    ...paymentFixture,
    key: "p1",
    case_id: "case",
    direction: "debit",
    account_holder: "ARRENDO SERV SA DE CV",
    from_name: "ARRENDO SERV SA DE CV",
    to_name: "EUGENIO HERNANDEZ",
    label_version: 1,
    label_sources: {
      from_name: { source: "account" },
      to_name: { source: "model_reading", label: "Read by Claude · not confirmed", explanation: "Read from s.pdf, page 4.", origin },
    },
    locator: { kind: "page_only", page: 4 },
  } as LedgerTransaction
}

function Row() {
  const { data } = useQuery<{ transactions: LedgerTransaction[] }>({ queryKey: KEY, queryFn: () => null as never, enabled: false })
  const row = data!.transactions[0]
  return (
    <div data-testid="row">
      <span data-testid="name">{row.to_name}</span>
      <PaymentLabelOrigin row={row} field="to_name" />
    </div>
  )
}

function mount(canEdit: boolean, openPanel?: (id: string) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(KEY, { transactions: [reading()], total: 1 })
  render(
    <QueryClientProvider client={client}>
      <FinancialAccessContext.Provider value={{ canEdit, canUpload: canEdit, ready: true, error: false }}>
        <ReadingCheckContext.Provider value={{ openPanel }}>
          <div data-testid="scroller" />
          <Row />
        </ReadingCheckContext.Provider>
      </FinancialAccessContext.Provider>
    </QueryClientProvider>
  )
  return client
}

beforeEach(() => {
  vi.resetAllMocks()
  window.scrollTo = vi.fn() as never
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/payment-labels/confirm")) return { case_id: "case", confirmed: 1, skipped: 0 }
    if (options?.method === "PUT") return { case_id: "case", updated: 1 }
    return {
      case_id: "case", transaction_id: "p1", evidence_file_id: "file", filename: "s.pdf",
      locator: { kind: "page_only", page: 4 }, locator_state: "stored", page: 4, page_count: 13,
      last_on_page: false, found: [], text_layer: false,
    }
  })
})

it("the label says what to do and clicking it shows the line, the reading and Confirm / Correct / Cancel", async () => {
  mount(true)
  expect(screen.getByTestId("model-reading-mark").textContent).toBe("Read by Claude · not confirmed — click to check")
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  const box = await screen.findByTestId("inline-reading-check")
  expect(within(box).getByTestId("inline-reading").textContent).toBe("EUGENIO HERNANDEZ")
  expect(within(box).getByText(/Read from s.pdf, page 4/)).toBeTruthy()
  for (const name of ["Confirm", "Correct", "Cancel"]) expect(within(box).getByRole("button", { name })).toBeTruthy()
  expect(await within(box).findByRole("group", { name: "Statement viewer controls" })).toBeTruthy()
})

it("Confirm saves through the confirm path, updates the row in place and takes the model label away", async () => {
  const client = mount(true)
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  fireEvent.click(await screen.findByRole("button", { name: "Confirm" }))
  await waitFor(() => expect(screen.queryByTestId("inline-reading-check")).toBeNull())
  const call = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/payment-labels/confirm"))!
  expect(call[1]).toMatchObject({ method: "POST", body: { transactions: [{ id: "p1", version: 1 }], fields: ["to_name"] } })
  expect(screen.queryByText(/not confirmed/)).toBeNull()
  expect(screen.getByTestId("name").textContent).toBe("EUGENIO HERNANDEZ")
  const saved = (client.getQueryData(KEY) as { transactions: LedgerTransaction[] }).transactions[0]
  expect(saved.label_sources?.to_name?.source).toBe("investigator")
  expect(saved.label_sources?.to_name?.confirmed_model_reading).toEqual(origin)
  expect(screen.getByTestId("row").textContent).toMatch(/Confirmed by Alex Rivera/)
})

it("Correct puts the person's name on the row and keeps what Claude read visible", async () => {
  mount(true)
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  fireEvent.click(await screen.findByRole("button", { name: "Correct" }))
  const field = screen.getByLabelText("Correct the name")
  fireEvent.change(field, { target: { value: "EUGENIO HERNANDEZ ROMERO" } })
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(screen.getByTestId("name").textContent).toBe("EUGENIO HERNANDEZ ROMERO"))
  const put = vi.mocked(fetchAPI).mock.calls.find(([, options]) => options?.method === "PUT")!
  expect(put[1]).toMatchObject({ body: { counterparty_name: "EUGENIO HERNANDEZ ROMERO", named_from: "statement" } })
  expect(screen.getByTestId("claude-read").textContent).toBe('Claude read: "EUGENIO HERNANDEZ"')
  expect(screen.getByTestId("row").textContent).toMatch(/Corrected by Alex Rivera/)
})

it("Esc cancels and focus returns to the label; Enter confirms", async () => {
  mount(true)
  const label = screen.getByRole("button", { name: /click to check/ })
  fireEvent.click(label)
  const box = await screen.findByTestId("inline-reading-check")
  fireEvent.keyDown(box, { key: "Escape" })
  await waitFor(() => expect(screen.queryByTestId("inline-reading-check")).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(label))
  fireEvent.click(label)
  fireEvent.keyDown(await screen.findByTestId("inline-reading-check"), { key: "Enter" })
  await waitFor(() => expect(vi.mocked(fetchAPI).mock.calls.some(([url]) => String(url).includes("/confirm"))).toBe(true))
})

it("a view-only user sees the line and the editor note, and no buttons that change anything", async () => {
  mount(false)
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  const box = await screen.findByTestId("inline-reading-check")
  expect(within(box).getByText("An editor of this case can confirm this.")).toBeTruthy()
  for (const name of ["Confirm", "Correct", "Cancel"]) expect(within(box).queryByRole("button", { name })).toBeNull()
  expect(await within(box).findByRole("group", { name: "Statement viewer controls" })).toBeTruthy()
})

it("Open in the check panel hands the payment to the page", async () => {
  const open = vi.fn()
  mount(true, open)
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  fireEvent.click(await screen.findByRole("button", { name: "Open in the check panel" }))
  expect(open).toHaveBeenCalledWith("p1")
})

it("the statement viewer rotates, pages through the document and returns to the payment", async () => {
  mount(true)
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  const box = await screen.findByTestId("inline-reading-check")
  await within(box).findByRole("group", { name: "Statement viewer controls" })
  fireEvent.click(within(box).getByRole("button", { name: "Next page" }))
  expect(within(box).getByText(/Page 5 of 13/)).toBeTruthy()
  expect(within(box).getByRole("img", { name: "Statement page 5" })).toBeTruthy()
  fireEvent.keyDown(within(box).getByRole("region", { name: "Statement page 5" }), { key: "PageDown" })
  expect(within(box).getByText(/Page 6 of 13/)).toBeTruthy()
  fireEvent.click(within(box).getByRole("button", { name: "Rotate statement right" }))
  expect(localStorage.getItem("statement-viewer-rotation:file")).toBe("90")
  fireEvent.click(within(box).getByRole("button", { name: "Back to this payment" }))
  expect(within(box).getByText(/Page 4 of 13/)).toBeTruthy()
  fireEvent.keyDown(within(box).getByRole("region", { name: /Statement page 4/ }), { key: "r" })
  expect(localStorage.getItem("statement-viewer-rotation:file")).toBe("180")
  localStorage.clear()
})

it("names the payer or the payee together with the account holder, never 'who paid this account'", () => {
  const out = reading()
  expect(payerPayeeQuestion(out)).toBe("Who did ARRENDO SERV SA DE CV pay? (the payee)")
  expect(payerPayeeQuestion({ ...out, direction: "credit" })).toBe("Who sent this money to ARRENDO SERV SA DE CV? (the payer)")
})

it("closing the check panel lands on the same row by its key, focused, with nothing else moved", async () => {
  const open = vi.fn()
  mount(true, open)
  const scrolled = vi.fn()
  Element.prototype.scrollIntoView = scrolled
  fireEvent.click(screen.getByRole("button", { name: /click to check/ }))
  fireEvent.click(await screen.findByRole("button", { name: "Open in the check panel" }))
  expect(open).toHaveBeenCalledWith("p1")
  // The page opens the panel; on close it calls this with the row it came from.
  ;(document.activeElement as HTMLElement | null)?.blur()
  showReadingRow("p1", true)
  await waitFor(() => expect(document.activeElement?.closest('[data-reading-row="p1"]')).toBeTruthy())
  expect(scrolled).toHaveBeenCalledWith({ block: "nearest" })
  expect(scrolled.mock.contexts[0]).toBe(document.querySelector('[data-reading-row="p1"]'))
})
