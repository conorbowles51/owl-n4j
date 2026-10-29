import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { modelReadingField, needsConfirm, needsName, withConfirmedName } from "../lib/payment-naming"
import { transactionCsv } from "../lib/transaction-csv"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import { PaymentNamingPanel } from "./PaymentNamingPanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: (url: string | null) => ({ objectUrl: url ? `blob:${url}` : null, loading: false, error: null }),
}))
vi.mock("@/components/ui/document-viewer", () => ({ DocumentViewer: () => null }))
vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: (pick: (state: { user: { name: string; username: string } }) => unknown) =>
    pick({ user: { name: "Alex Rivera", username: "alex" } }),
}))

const origin = {
  kind: "model" as const,
  model: "Claude",
  for: { name: "Neil Byrne" },
  at: "2026-10-28T10:00:00+00:00",
  citation: { page: 4, file: "bbva-dic-2024.pdf" },
}

function read(key: string, name = "EUGENIO HERNANDEZ ROMERO"): LedgerTransaction {
  return {
    ...paymentFixture,
    key,
    amount_minor: "150000",
    currency: "MXN",
    direction: "debit",
    description: "T17 SPEI ENVIADO BANORTE PAGO FACTURA",
    from_name: "ARRENDO SERV SA DE CV",
    to_name: name,
    label_version: 1,
    label_sources: {
      from_name: { source: "account" },
      to_name: {
        source: "model_reading",
        label: "Read by Claude · not confirmed",
        explanation: "Read by Claude for Neil Byrne on 2026-10-28; not confirmed by a person. Read from bbva-dic-2024.pdf, page 4.",
        origin,
      },
    },
    locator: { kind: "page_only", page: 4 },
  } as LedgerTransaction
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/payment-labels/confirm"))
      return { case_id: "case", confirmed: 1, skipped: 0 }
    if (options?.method === "PUT" || options?.method === "POST")
      return { case_id: "case", updated: (options.body as { transactions: unknown[] }).transactions.length }
    const id = decodeURIComponent(String(url).split("/ledger/")[1].split("/")[0])
    return {
      case_id: "case", transaction_id: id, evidence_file_id: "file", filename: "bbva-dic-2024.pdf",
      locator: { kind: "page_only", page: 4 }, locator_state: "stored", page: 4, page_count: 13,
      last_on_page: false, found: [], text_layer: false,
    }
  })
})

function Harness({ rows }: { rows: LedgerTransaction[] }) {
  const [current, setCurrent] = useState(rows[0].key)
  return (
    <>
      <p data-testid="current">{current}</p>
      <PaymentNamingPanel
        caseId="case"
        rows={rows}
        queue={rows.filter(needsConfirm)}
        currentId={current}
        onMove={setCurrent}
        onClose={() => undefined}
        mode="confirm"
      />
    </>
  )
}

function mount(rows: LedgerTransaction[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(["financial-ledger", "case", null], { transactions: rows, total: rows.length })
  render(
    <QueryClientProvider client={client}>
      <Harness rows={rows} />
    </QueryClientProvider>
  )
  return client
}

it("finds names a model read that no person has confirmed, and never treats them as unnamed", () => {
  const row = read("a")
  expect(modelReadingField(row)).toBe("to_name")
  expect(needsConfirm(row)).toBe(true)
  expect(needsName(row)).toBe(false)
  const confirmed = withConfirmedName(row, "to_name", "Confirmed by Alex Rivera from the statement on 2026-10-29.")
  expect(confirmed.to_name).toBe(row.to_name)
  expect(confirmed.label_sources?.to_name?.source).toBe("investigator")
  expect(confirmed.label_sources?.to_name?.confirmed_model_reading).toEqual(origin)
  expect(needsConfirm(confirmed)).toBe(false)
})

it("shows the reading as Claude's with its citation, never as a person's name", () => {
  render(<PaymentLabelOrigin row={read("a")} field="to_name" />)
  const mark = screen.getByTestId("model-reading-mark")
  expect(mark.textContent).toBe("Read by Claude · not confirmed")
  expect(mark.getAttribute("title")).toContain("page 4")
  expect(screen.queryByText(/Read from bbva-dic-2024.pdf, page 4/)).toBeNull()
  fireEvent.click(mark)
  expect(screen.getByText(/Read from bbva-dic-2024.pdf, page 4/)).toBeTruthy()
})

it("Enter on the reading as read confirms it with one call and opens the next one", async () => {
  mount([read("a"), read("b", "OTRA PERSONA")])
  const field = (await screen.findByLabelText("Name who was paid")) as HTMLInputElement
  expect(field.value).toBe("EUGENIO HERNANDEZ ROMERO")
  expect(screen.getByTestId("model-reading").textContent).toContain("Read by Claude · not confirmed")
  expect(screen.getByRole("button", { name: "Confirm and next (Enter)" })).toBeTruthy()
  fireEvent.keyDown(field, { key: "Enter" })
  await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("b"))
  const calls = vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes("/payment-labels/confirm"))
  expect(calls).toHaveLength(1)
  expect(calls[0][1]?.body).toEqual({ transactions: [{ id: "a", version: 1 }], fields: ["to_name"] })
  expect(vi.mocked(fetchAPI).mock.calls.filter(([, o]) => o?.method === "PUT")).toHaveLength(0)
})

it("a changed name is saved as the person's correction, not a confirmation", async () => {
  mount([read("a"), read("b")])
  const field = (await screen.findByLabelText("Name who was paid")) as HTMLInputElement
  fireEvent.change(field, { target: { value: "EUGENIO HERNANDEZ ROMERO SA" } })
  expect(screen.getByRole("button", { name: "Save and next (Enter)" })).toBeTruthy()
  fireEvent.keyDown(field, { key: "Enter" })
  await waitFor(() => expect(vi.mocked(fetchAPI).mock.calls.some(([, o]) => o?.method === "PUT")).toBe(true))
  const put = vi.mocked(fetchAPI).mock.calls.find(([, o]) => o?.method === "PUT")!
  expect(put[1]?.body).toMatchObject({ transactions: [{ id: "a", version: 1 }], counterparty_name: "EUGENIO HERNANDEZ ROMERO SA" })
  expect(vi.mocked(fetchAPI).mock.calls.some(([url]) => String(url).includes("/confirm"))).toBe(false)
})

it("the export says a name was read by Claude and not confirmed, with the page", () => {
  const csv = transactionCsv([read("a")])
  expect(csv).toContain("read by Claude, not confirmed (bbva-dic-2024.pdf page 4)")
})
