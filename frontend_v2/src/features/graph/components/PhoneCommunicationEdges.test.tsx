import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** 07 J-3 (J-3b, Graph start): a communication edge opens Conversations Between A and B with the same count. */
const api = vi.hoisted(() => ({ getLinkEdges: vi.fn(), getSettings: vi.fn(), freezeSelection: vi.fn(), getFinancialPresence: vi.fn(async () => ({ has_financial_evidence: true })) }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { PhoneCommunicationEdges } from "./PhoneCommunicationEdges"

const A = "phone:+12025550143"
const B = "app:telegram:id:@synthetic_ben"
const nodes = [
  { key: `phone-identity:${A}`, label: "+1 202-555-0143", type: "PhoneIdentity", properties: {} },
  { key: `phone-identity:${B}`, label: "@synthetic_ben", type: "PhoneIdentity", properties: {} },
]
const edges = [
  { source: `phone-identity:${A}`, target: `phone-identity:${B}`, type: "COMMUNICATED" },
  { source: `phone-identity:${A}`, target: "phone-extraction:x", type: "APPEARS_ON" },
]

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname}{l.search}</p>
}

describe("communication edges on the Graph", () => {
  it("counts each pair as Conversations does and opens Between A and B", async () => {
    api.getLinkEdges.mockResolvedValue({ edges: [{
      a: { identity_key: A, label: "Synthetic Ana" }, b: { identity_key: B, label: "Synthetic Ben" }, label: "",
      communication: { messages_ab: 2, messages_ba: 1, calls_ab: 0, calls_ba: 1, emails_ab: 0, emails_ba: 0,
        first_instant: null, last_instant: null, phones: ["C1"], no_time_count: 0 } }] })
    render(
      <MemoryRouter initialEntries={["/cases/case-1/graph"]}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <Routes>
            <Route path="/cases/:id/graph" element={<PhoneCommunicationEdges caseId="case-1" nodes={nodes} edges={edges} />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    )
    const region = screen.getByRole("region", { name: "Messages and calls between people" })
    expect(region.textContent).toContain("(1 pair)")
    const button = await screen.findByRole("button", { name: "3 messages and 1 call between Synthetic Ana and Synthetic Ben" })
    expect(api.getLinkEdges).toHaveBeenCalledWith("case-1", [{ identity_key: A }, { identity_key: B }])
    fireEvent.click(button)
    const where = screen.getByTestId("where").textContent || ""
    expect(where.startsWith("/cases/case-1/conversations?")).toBe(true)
    const q = new URLSearchParams(where.split("?")[1])
    expect([q.get("tab"), q.get("people"), q.get("mode")]).toEqual(["people", `${A},${B}`, "between"])
  })

  it("recounts each pair for the chosen window, restyles from that count and opens Conversations for the window (03 14.3, R-3)", async () => {
    api.getLinkEdges.mockReset()
    api.getLinkEdges.mockImplementation(async (_c: string, _s: unknown, opts?: { fromInstant?: string }) => ({ edges: [{
      a: { identity_key: A, label: "Synthetic Ana" }, b: { identity_key: B, label: "Synthetic Ben" }, label: "",
      communication: { messages_ab: opts?.fromInstant ? 1 : 2, messages_ba: opts?.fromInstant ? 0 : 1, calls_ab: 0, calls_ba: 0, emails_ab: 0, emails_ba: 0,
        first_instant: null, last_instant: null, phones: ["C1"], no_time_count: 0 } }] }))
    render(
      <MemoryRouter initialEntries={["/cases/case-1/graph"]}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <Routes>
            <Route path="/cases/:id/graph" element={<PhoneCommunicationEdges caseId="case-1" nodes={nodes} edges={edges} />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    )
    await screen.findByRole("button", { name: "3 messages between Synthetic Ana and Synthetic Ben" })
    fireEvent.change(screen.getByLabelText("Edges from"), { target: { value: "2023-03-01" } })
    fireEvent.change(screen.getByLabelText("to"), { target: { value: "2023-03-31" } })
    fireEvent.click(screen.getByRole("button", { name: "Count this window" }))
    const button = await screen.findByRole("button", { name: "1 message between Synthetic Ana and Synthetic Ben in the window" })
    expect(api.getLinkEdges).toHaveBeenLastCalledWith("case-1", [{ identity_key: A }, { identity_key: B }],
      { fromInstant: "2023-03-01T00:00:00Z", toInstant: "2023-03-31T23:59:59Z" })
    const { useEdgeWindow, edgeKey, windowStyle } = await import("../stores/edge-window.store")
    await waitFor(() => expect(useEdgeWindow.getState().counts[edgeKey(A, B)]).toBe(1))
    const st = useEdgeWindow.getState()
    expect(windowStyle("COMMUNICATED", `phone-identity:${A}`, `phone-identity:${B}`, st.window, st.counts)?.dashed).toBe(false)
    expect(windowStyle("COMMUNICATED", `phone-identity:${A}`, `phone-identity:${B}`, st.window, { [edgeKey(A, B)]: 0 })?.dashed).toBe(true)
    expect(windowStyle("APPEARS_ON", `phone-identity:${A}`, "phone-extraction:x", st.window, st.counts)).toBeNull()
    fireEvent.click(button)
    const q = new URLSearchParams((screen.getByTestId("where").textContent || "").split("?")[1])
    expect([q.get("from"), q.get("to"), q.get("notime"), q.get("mode")]).toEqual(["2023-03-01T00:00:00Z", "2023-03-31T23:59:59Z", "0", "between"])
  })

  it("shows nothing when the graph has no communication edge", () => {
    const { container } = render(
      <MemoryRouter><QueryClientProvider client={new QueryClient()}>
        <PhoneCommunicationEdges caseId="case-1" nodes={nodes} edges={[edges[1]]} />
      </QueryClientProvider></MemoryRouter>,
    )
    expect(container.textContent).toBe("")
  })
})

/** CO-1 cell "Graph edges" (07 6.5): Add to… on chosen pairs keeps each pair's Conversations scope, only on request. */
describe("adding pairs from the Graph", () => {
  it("keeps a chosen pair as the selection its edge opens, then offers Add to…; nothing is kept on a tick", async () => {
    api.getLinkEdges.mockResolvedValue({ edges: [] })
    api.getSettings.mockResolvedValue({ case_id: "case-1", time_zone: null, effective: { name: "UTC", basis: "", note: null }, updated_at: null, updated_by: null })
    api.freezeSelection.mockResolvedValue({ id: "sel-1", record_count: 5, event_count: 4, words: "Messages and calls between +1 202-555-0143 and @synthetic_ben" })
    render(
      <MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PhoneCommunicationEdges caseId="case-1" nodes={nodes} edges={edges} />
      </QueryClientProvider></MemoryRouter>,
    )
    expect(api.getSettings).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("checkbox", { name: "Choose +1 202-555-0143 and @synthetic_ben to add" }))
    expect(api.freezeSelection).not.toHaveBeenCalled()
    const keep = await screen.findByRole("button", { name: "Add this pair's messages to…" })
    await waitFor(() => expect(keep).not.toBeDisabled())
    fireEvent.click(keep)
    await waitFor(() => expect(api.freezeSelection).toHaveBeenCalledTimes(1))
    const [filter, words] = api.freezeSelection.mock.calls[0]
    expect(filter).toMatchObject({ case_id: "case-1", participants: [A, B], participant_mode: "between", group_scope: "direct" })
    expect(filter.collapse_copies).toBeUndefined()   // copies collapsed, as the edge counts them
    expect(words).toBe("Messages and calls between +1 202-555-0143 and @synthetic_ben")
    expect(await screen.findByRole("button", { name: /Add to/ })).toBeInTheDocument()
  })
})
