import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

/** 07 J-3 (J-3b, Graph start): a communication edge opens Conversations Between A and B with the same count. */
const api = vi.hoisted(() => ({ getLinkEdges: vi.fn(), getSettings: vi.fn(), freezeSelection: vi.fn(), getFinancialPresence: vi.fn(async () => ({ has_financial_evidence: true })) }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { PhoneCommunicationEdges } from "./PhoneCommunicationEdges"
import { contactSummary, contactWords } from "../lib/contact-words"
import { usePairHighlight, litPairs, isLitLink } from "../stores/pair-highlight.store"
import { edgeKey } from "../stores/edge-window.store"
import type { GraphEdge } from "@/types/graph.types"

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

const comm = (m: number, c: number, e: number) => ({ edges: [{
  a: { identity_key: A, label: "Synthetic Ana" }, b: { identity_key: B, label: "Synthetic Ben" }, label: "",
  communication: { messages_ab: m, messages_ba: 0, calls_ab: c, calls_ba: 0, emails_ab: e, emails_ba: 0,
    first_instant: null, last_instant: null, phones: ["C1"], no_time_count: 0 } }] })

function renderPanel(props: { edges?: GraphEdge[]; shownKeys?: Set<string>; caseId?: string } = {}) {
  return render(
    <MemoryRouter initialEntries={["/cases/case-1/graph"]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Routes>
          <Route path="/cases/:id/graph" element={<PhoneCommunicationEdges caseId={props.caseId ?? "case-1"} nodes={nodes} edges={props.edges ?? edges} shownKeys={props.shownKeys} />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}
const openPanel = () => fireEvent.click(screen.getByRole("button", { expanded: false }))

beforeEach(() => {
  localStorage.clear()
  api.getLinkEdges.mockReset()
  api.getSettings.mockClear()
  api.freezeSelection.mockClear()
  usePairHighlight.setState({ hover: null, chosen: [] })
})

describe("People in contact on the Graph (lx-graphclarity B)", () => {
  it("is closed by default to one plain line, opens on a click and remembers that per case", async () => {
    api.getLinkEdges.mockResolvedValue(comm(3, 1, 0))
    const { unmount } = renderPanel()
    const region = screen.getByRole("region", { name: "People in contact" })
    expect(region.textContent).toContain("2 people on the phones messaged, called or emailed each other. See how often")
    expect(screen.queryByRole("table")).toBeNull()
    expect(api.getLinkEdges).not.toHaveBeenCalled()
    openPanel()
    expect(await screen.findByRole("table")).toBeInTheDocument()
    expect(localStorage.getItem("loupe.graph.people-in-contact.case-1")).toBe("open")
    unmount()
    renderPanel()
    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument()
  })

  it("says what the closed panel holds in words", () => {
    expect(contactSummary(20)).toBe("20 pairs of people on the phones messaged, called or emailed each other. See who and how often")
  })

  it("counts each pair as Conversations does and Show their messages opens Between A and B", async () => {
    api.getLinkEdges.mockResolvedValue(comm(3, 1, 0))
    renderPanel()
    openPanel()
    const row = (await screen.findAllByTestId("contact-pair"))[0]
    await waitFor(() => expect(row.textContent).toContain("3 messages and 1 call"))
    expect(row.textContent).toContain("Synthetic Ana and Synthetic Ben")
    expect(screen.getByRole("columnheader", { name: "Choose" })).toBeInTheDocument()
    expect(api.getLinkEdges).toHaveBeenCalledWith("case-1", [{ identity_key: A }, { identity_key: B }])
    fireEvent.click(screen.getByRole("button", { name: "Show the messages between Synthetic Ana and Synthetic Ben" }))
    const where = screen.getByTestId("where").textContent || ""
    expect(where.startsWith("/cases/case-1/conversations?")).toBe(true)
    const q = new URLSearchParams(where.split("?")[1])
    expect([q.get("tab"), q.get("people"), q.get("mode")]).toEqual(["people", `${A},${B}`, "between"])
  })

  it("leaves zero counts out and uses no internal words", async () => {
    expect(contactWords(0, 0, 1)).toBe("1 email")
    expect(contactWords(43, 4, 0)).toBe("43 messages and 4 calls")
    expect(contactWords(3, 1, 2)).toBe("3 messages, 1 call and 2 emails")
    expect(contactWords(0, 0, 0)).toBe("No contact")
    api.getLinkEdges.mockResolvedValue(comm(0, 0, 1))
    renderPanel()
    openPanel()
    const row = (await screen.findAllByTestId("contact-pair"))[0]
    await waitFor(() => expect(row.textContent).toContain("1 email"))
    const region = screen.getByRole("region", { name: "People in contact" })
    expect(region.textContent).not.toMatch(/\b0 messages|[Ee]dges?\b|window|Flow view/)
  })

  it("recounts each pair for the chosen dates, restyles from that count and opens Conversations for them (03 14.3, R-3)", async () => {
    api.getLinkEdges.mockImplementation(async (_c: string, _s: unknown, opts?: { fromInstant?: string }) => comm(opts?.fromInstant ? 1 : 3, 0, 0))
    renderPanel()
    openPanel()
    const row = (await screen.findAllByTestId("contact-pair"))[0]
    await waitFor(() => expect(row.textContent).toContain("3 messages"))
    fireEvent.change(screen.getByLabelText("Count only between"), { target: { value: "2023-03-01" } })
    fireEvent.change(screen.getByLabelText("and"), { target: { value: "2023-03-31" } })
    fireEvent.click(screen.getByRole("button", { name: "Count" }))
    await waitFor(() => expect(row.textContent).toContain("1 message in these dates"))
    expect(api.getLinkEdges).toHaveBeenLastCalledWith("case-1", [{ identity_key: A }, { identity_key: B }],
      { fromInstant: "2023-03-01T00:00:00Z", toInstant: "2023-03-31T23:59:59Z" })
    const { useEdgeWindow, windowStyle } = await import("../stores/edge-window.store")
    await waitFor(() => expect(useEdgeWindow.getState().counts[edgeKey(A, B)]).toBe(1))
    const st = useEdgeWindow.getState()
    expect(windowStyle("COMMUNICATED", `phone-identity:${A}`, `phone-identity:${B}`, st.window, st.counts)?.dashed).toBe(false)
    expect(windowStyle("COMMUNICATED", `phone-identity:${A}`, `phone-identity:${B}`, st.window, { [edgeKey(A, B)]: 0 })?.dashed).toBe(true)
    fireEvent.click(screen.getByRole("button", { name: "Show the messages between Synthetic Ana and Synthetic Ben" }))
    const q = new URLSearchParams((screen.getByTestId("where").textContent || "").split("?")[1])
    expect([q.get("from"), q.get("to"), q.get("notime"), q.get("mode")]).toEqual(["2023-03-01T00:00:00Z", "2023-03-31T23:59:59Z", "0", "between"])
  })

  it("clears the dates with Clear dates", async () => {
    api.getLinkEdges.mockResolvedValue(comm(3, 0, 0))
    renderPanel()
    openPanel()
    fireEvent.change(screen.getByLabelText("Count only between"), { target: { value: "2023-03-01" } })
    fireEvent.change(screen.getByLabelText("and"), { target: { value: "2023-03-31" } })
    fireEvent.click(screen.getByRole("button", { name: "Count" }))
    fireEvent.click(await screen.findByRole("button", { name: "Clear dates" }))
    expect(screen.getByText("Counts cover all dates.")).toBeInTheDocument()
  })

  it("highlights the pair on the graph when pointed at or chosen", async () => {
    api.getLinkEdges.mockResolvedValue(comm(3, 0, 0))
    renderPanel()
    openPanel()
    const row = (await screen.findAllByTestId("contact-pair"))[0]
    fireEvent.mouseEnter(row)
    expect(usePairHighlight.getState().hover).toBe(edgeKey(A, B))
    fireEvent.mouseLeave(row)
    expect(usePairHighlight.getState().hover).toBeNull()
    fireEvent.click(screen.getByRole("checkbox", { name: /^Choose / }))
    expect(usePairHighlight.getState().chosen).toEqual([edgeKey(A, B)])
    const lit = litPairs(null, usePairHighlight.getState().chosen)
    expect(lit.nodes).toEqual(new Set([`phone-identity:${A}`, `phone-identity:${B}`]))
    expect(isLitLink("COMMUNICATED", `phone-identity:${B}`, `phone-identity:${A}`, lit.links)).toBe(true)
    expect(isLitLink("APPEARS_ON", `phone-identity:${A}`, "phone-extraction:x", lit.links)).toBe(false)
  })

  it("says when the graph does not draw one of the two", async () => {
    api.getLinkEdges.mockResolvedValue({ edges: [] })
    renderPanel({ shownKeys: new Set([`phone-identity:${A}`]) })
    openPanel()
    expect(await screen.findByText("@synthetic_ben is not drawn on the graph now.")).toBeInTheDocument()
  })

  it("lists the busiest pair first", async () => {
    const C = "phone:+12025550199"
    const many = [
      { source: `phone-identity:${A}`, target: `phone-identity:${B}`, type: "COMMUNICATED", contact: 2 },
      { source: `phone-identity:${A}`, target: `phone-identity:${C}`, type: "COMMUNICATED", contact: 9 },
    ]
    api.getLinkEdges.mockResolvedValue({ edges: [] })
    renderPanel({ edges: many })
    openPanel()
    const rows = await screen.findAllByTestId("contact-pair")
    expect(rows[0].textContent).toContain(C)
    expect(rows[1].textContent).toContain("@synthetic_ben")
  })

  it("shows nothing when the graph has no pair in contact", () => {
    const { container } = renderPanel({ edges: [edges[1]] })
    expect(container.textContent).toBe("")
  })
})

/** CO-1 cell "Graph edges" (07 6.5): Add to… on chosen pairs keeps each pair's Conversations scope, only on request. */
describe("adding pairs from the Graph", () => {
  it("keeps a chosen pair as the selection its row opens, then offers Add to…; nothing is kept on a tick", async () => {
    api.getLinkEdges.mockResolvedValue({ edges: [] })
    api.getSettings.mockResolvedValue({ case_id: "case-1", time_zone: null, effective: { name: "UTC", basis: "", note: null }, updated_at: null, updated_by: null })
    api.freezeSelection.mockResolvedValue({ id: "sel-1", record_count: 5, event_count: 4, words: "Messages and calls between +1 202-555-0143 and @synthetic_ben" })
    renderPanel()
    openPanel()
    expect(api.getSettings).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole("checkbox", { name: "Choose +1 202-555-0143 and @synthetic_ben" }))
    expect(api.freezeSelection).not.toHaveBeenCalled()
    const keep = await screen.findByRole("button", { name: "Add the chosen pair's messages to a dossier, theory or note" })
    await waitFor(() => expect(keep).not.toBeDisabled())
    fireEvent.click(keep)
    await waitFor(() => expect(api.freezeSelection).toHaveBeenCalledTimes(1))
    const [filter, words] = api.freezeSelection.mock.calls[0]
    expect(filter).toMatchObject({ case_id: "case-1", participants: [A, B], participant_mode: "between", group_scope: "direct" })
    expect(filter.collapse_copies).toBeUndefined()   // copies collapsed, as the row counts them
    expect(words).toBe("Messages and calls between +1 202-555-0143 and @synthetic_ben")
    expect(await screen.findByRole("button", { name: /Add to/ })).toBeInTheDocument()
  })
})
