import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { SearchResult } from "../api"

/** Loupe-wide search dialog (03 section 11.4) with the server stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({ searchCase: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { HitLine, SearchDialog } from "./SearchDialog"

const hit = (over: Record<string, unknown>) => ({ kind: "message", title: "C3 WhatsApp message", snippet: { before: "Meet ", match: "Jose", after: " at the dock" }, record_uid: "r1", evidence_file_id: null, open: { screen: "conversations", params: { phone: "e1", thread: "chat:e1:t", event: "v1", q: "jose" } }, ...over })

function result(over: Partial<SearchResult> = {}): SearchResult {
  return {
    query: "jose", folded_query: "jose", exact: false, complete: true, limits: [], short: null,
    groups: [
      { group: "messages", total: 41, items: [hit({})], next_cursor: "1", score: 2 },
      { group: "calls", total: 0, items: [], next_cursor: null, score: 0 },
      { group: "people", total: 1, items: [hit({ kind: "identity", title: "Jose", record_uid: null, identity_key: "phone:+12025550143", open: { screen: "people", params: { people: "phone:+12025550143" } } })], next_cursor: null, score: 3 },
      { group: "documents", total: 2, items: [hit({ kind: "document", title: "synthetic.pdf", record_uid: null, evidence_file_id: "f1", page: 2, open: { screen: "document", params: { evidence_file_id: "f1", page: 2 } } })], next_cursor: "1", score: 1.1, note: "3 documents are still being prepared for this search; they are matched as typed, without folding." },
    ],
    not_searched: [{ group: "media", reason: "Text read from photos, audio and video is not searched yet." }],
    ...over,
  } as SearchResult
}

function Where() {
  const l = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <p data-testid="where">{l.pathname + l.search}</p>
      <button data-testid="back" onClick={() => navigate(-1)} />
    </>
  )
}

function page() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cases/case-1/graph"]}>
        <Routes>
          <Route path="*" element={<><SearchDialog caseId="case-1" /><Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openAndType(text: string) {
  act(() => void document.dispatchEvent(new CustomEvent("owl:toggle-command-palette")))
  const box = await screen.findByPlaceholderText("Search words, names, numbers or accounts")
  fireEvent.change(box, { target: { value: text } })
  return box
}

describe("Search dialog", () => {
  beforeEach(() => {
    // cmdk and the dialog measure their lists; jsdom has no ResizeObserver and no scrollIntoView
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
    Element.prototype.scrollIntoView = () => {}
    sessionStorage.clear()
    api.searchCase.mockReset()
    api.searchCase.mockResolvedValue(result())
  })

  it("Ctrl/Cmd+K pressed again while open keeps the box open and selects the words, so typing starts anew (07 J-6)", async () => {
    page()
    const box = (await openAndType("synthetic")) as HTMLInputElement
    act(() => void document.dispatchEvent(new CustomEvent("owl:toggle-command-palette")))
    expect(screen.getByPlaceholderText("Search words, names, numbers or accounts")).toBe(box)
    expect(document.activeElement).toBe(box)
    expect([box.selectionStart, box.selectionEnd]).toEqual([0, "synthetic".length])
  })

  it("opens on Ctrl/Cmd+K's event and shows each group's exact total, notes and what was not searched", async () => {
    page()
    await openAndType("jose")
    expect(await screen.findByText("Messages (41)")).toBeInTheDocument()
    expect(screen.getByText("People and identifiers (1)")).toBeInTheDocument()
    expect(screen.getByText("Documents and transcripts (2)")).toBeInTheDocument()
    expect(screen.getByText(/3 documents are still being prepared/)).toBeInTheDocument()
    expect(screen.getByText("No matches in: Calls.")).toBeInTheDocument()
    expect(screen.getByText("Text read from photos, audio and video is not searched yet.")).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /Show all 41 in Conversations/ })).toBeInTheDocument()
    await waitFor(() => expect(api.searchCase).toHaveBeenCalledWith("case-1", "jose", false, expect.anything()))
  })

  it("Enter opens the top hit of the group whose top hit scores highest (the Enter rule)", async () => {
    page()
    const box = await openAndType("jose")
    await screen.findByText("People and identifiers (1)")
    await waitFor(() => expect(screen.getAllByRole("option").filter((o) => o.getAttribute("aria-selected") === "true").map((o) => o.textContent)).toEqual([expect.stringMatching(/^Jose/)]))
    fireEvent.keyDown(box, { key: "Enter" })
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/cases/case-1/conversations?tab=people&people=phone%3A%2B12025550143"))
    expect(JSON.parse(sessionStorage.getItem("loupe.search.recent") ?? "[]")).toEqual(["jose"])
  })

  it("a message hit opens its whole thread at that message with the search marked (S-8); Show all opens Conversations with the text", async () => {
    page()
    await openAndType("jose")
    fireEvent.click(await screen.findByRole("option", { name: /^C3 WhatsApp message/ }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/cases/case-1/phones/e1/records/conversations?thread=chat%3Ae1%3At&at=v1&hl=jose"))
    await openAndType("jose")
    fireEvent.click(await screen.findByRole("option", { name: /Show all 41 in Conversations/ }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/cases/case-1/conversations?q=jose&kinds=message%2Cchat_activity"))
  })

  it("a payments group shows its totals per currency, verified apart from p3, and a hit opens that payment", async () => {
    const pop = (credits: string, debits: string, cc: number, dc: number) => ({ credits_minor: credits, debits_minor: debits, credit_count: cc, debit_count: dc })
    api.searchCase.mockResolvedValue(result({ query: "acme", folded_query: "acme", groups: [{
      group: "payments", total: 3, next_cursor: null, score: 1.05,
      searched: "Names Loupe suggests for a payment are not searched.",
      totals: { currencies: [{ currency: "USD", verified: pop("0", "0", 0, 0), p3: pop("123456", "1000", 2, 1) }], counted_rows: 3, not_counted_rows: 0 },
      items: [hit({ kind: "payment", title: "Wire to ACME", record_uid: null, transaction_id: "t-1", cite: "txn://t-1",
        date: "2024-03-12", amount_minor: "123456", currency: "USD", direction: "credit", from_name: "ACME", to_name: "Synthetic Co",
        included_in_totals: true, snippet: { before: "Wire to ", match: "ACME", after: "" }, open: { screen: "payment", params: { transaction_id: "t-1" } } })],
    }] }))
    page()
    await openAndType("acme")
    expect(await screen.findByText("Payments (3)")).toBeInTheDocument()
    expect(screen.getByTestId("payment-totals").textContent).toContain("USD: verified in USD 0.00 (0), out USD 0.00 (0) · read from statements, not verified: in USD 1,234.56 (2), out USD 10.00 (1)")
    expect(screen.getByText("Names Loupe suggests for a payment are not searched.")).toBeInTheDocument()
    fireEvent.click(await screen.findByRole("option", { name: /In USD 1,234.56/ }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/cases/case-1/financial?view=transactions&payment=t-1"))
  })

  it("a short query says text needs 3 letters, and Exact characters is sent", async () => {
    api.searchCase.mockResolvedValue(result({ query: "jo", short: "Type at least 3 letters.", groups: [] }))
    page()
    await openAndType("jo")
    expect(await screen.findByText("Type at least 3 letters.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("checkbox", { name: "Exact characters" }))
    await waitFor(() => expect(api.searchCase).toHaveBeenCalledWith("case-1", "jo", true, expect.anything()))
  })
  it("Back from an opened hit shows the same results again (S-9)", async () => {
    page()
    await openAndType("jose")
    fireEvent.click(await screen.findByText("synthetic.pdf · page 2", { exact: false }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).not.toBe("/cases/case-1/graph"))
    expect(screen.queryByPlaceholderText("Search words, names, numbers or accounts")).toBeNull()
    fireEvent.click(screen.getByTestId("back"))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/cases/case-1/graph"))
    expect(await screen.findByPlaceholderText("Search words, names, numbers or accounts")).toHaveValue("jose")
    expect(await screen.findByText("People and identifiers (1)")).toBeInTheDocument()
  })
  it("says when a phone is still being read, so no total reads as whole", async () => {
    api.searchCase.mockResolvedValue(result({ complete: false, limits: [{ kind: "phone_incomplete", message: "C9 is still being read. Results will be incomplete until it finishes." }] }))
    page()
    await openAndType("jose")
    expect(await screen.findByRole("alert")).toHaveTextContent("C9 is still being read. Results will be incomplete until it finishes.")
  })
})

describe("HitLine for a machine translation (05 17.5)", () => {
  it("shows the translation's match, its label, and cites the original", () => {
    render(
      <HitLine
        hit={{
          kind: "machine_translation", title: "C1 machine translation of a message", snippet: { before: "Bring the ", match: "blue package", after: "." },
          record_uid: "r1", evidence_file_id: null, machine_generated: true, translated_from: "Spanish",
          label: "Machine translation (local, opus-mt-es-en c96e2c5, transformers 5.3.0), not checked by a person. The original is above.",
          original: { text: "Trae el paquete azul.", clipped: false, chars: 21 }, open: { screen: "conversations", params: {} },
        }}
      />,
    )
    expect(screen.getByText("blue package")).toBeInTheDocument()
    expect(screen.getByTestId("hit-original")).toHaveTextContent("Original (Spanish): Trae el paquete azul.")
    expect(screen.getByText(/^Machine translation \(local, opus-mt-es-en/)).toBeInTheDocument()
  })
})
