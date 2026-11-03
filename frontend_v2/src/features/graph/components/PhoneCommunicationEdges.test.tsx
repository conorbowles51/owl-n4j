import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** 07 J-3 (J-3b, Graph start): a communication edge opens Conversations Between A and B with the same count. */
const api = vi.hoisted(() => ({ getLinkEdges: vi.fn() }))
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

  it("shows nothing when the graph has no communication edge", () => {
    const { container } = render(
      <MemoryRouter><QueryClientProvider client={new QueryClient()}>
        <PhoneCommunicationEdges caseId="case-1" nodes={nodes} edges={[edges[1]]} />
      </QueryClientProvider></MemoryRouter>,
    )
    expect(container.textContent).toBe("")
  })
})
