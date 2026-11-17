import { describe, expect, it, vi, beforeEach } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { currentQuery, relationAPI, setCurrentQuery, toMembers, type RelationResult } from "./api"
import { LookIntoButton } from "./LookIntoButton"
import { RelationsPage } from "./RelationsPage"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { render as plainRender } from "@testing-library/react"

vi.mock("@/features/phones/collect-targets", () => ({ useCollectTargets: () => ({ targets: [{ kind: "theory", id: "t1", label: "Acme pays Ann" }], note: null, loading: false, error: null }) }))

const result: RelationResult = {
  says: "These are records that occur together. They do not show why.",
  items: [{ ref: "a", type: "financial_transaction", id: "1", label: "Payment", at: "2026-03-01T00:00:00+00:00" }, { ref: "b", type: "evidence", id: "2", label: "Contract", at: null }],
  candidates: [{ kind: "shared_identifier", members: ["a", "b"], key: "name", strength: "strong", reasons: ["Both carry the same name."], chance: { words: "“Harbor” appears on 3 of 900 ledger rows in the case.", reading: "none", share_of_days: null } }],
  no_links: [{ members: ["a", "b"], analyses: ["time_proximity"], searched: ["dates of both"], says: "Nothing found by the analyses that apply. This is what was searched, not proof that no link exists.", out_of_reach: ["no date on record"] }],
  analyses: [{ id: "time_proximity", title: "Close in time", pairs: 1, found: 0, existing: null }],
  out_of_reach: [], counts: { items: 2, pairs: 1, candidates: 1, no_links: 1, by_strength: { strong: 1, moderate: 0, weak: 0, faint: 0 } }, seconds: 1.2,
}

function wrap(ui: React.ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe("toMembers", () => {
  it("names what it cannot compare instead of dropping it", () => {
    const out = toMembers([
      { target_type: "financial_transaction", target_id: "p1", target_label: "Payment" },
      { target_type: "evidence_passage", target_id: "f:h:1:9" },
      { target_type: "interview", target_id: "i1" },
      { target_type: "agent_answer", target_id: "x" },
    ])
    expect(out.members.map((m) => m.type)).toEqual(["financial_transaction", "evidence_passage"])
    expect(out.skipped).toEqual([{ type: "interview", count: 1 }, { type: "agent_answer", count: 1 }])
  })
  it("reads a group's members", () => {
    const out = toMembers(undefined, { group_type: "graph_selection", how: {}, words: "w", members: [{ type: "graph_entity", id: "k", label: "Ann" }, { type: "history_step", id: "s" }] })
    expect(out.members).toEqual([{ type: "graph_entity", id: "k", label: "Ann" }])
    expect(out.skipped).toEqual([{ type: "history_step", count: 1 }])
  })
})

describe("the look in progress", () => {
  it("round-trips through the browser", () => {
    expect(currentQuery("c1")).toBeNull()
    setCurrentQuery("c1", { id: "g1", count: 3 })
    expect(currentQuery("c1")).toEqual({ id: "g1", count: 3 })
    setCurrentQuery("c1", null)
    expect(currentQuery("c1")).toBeNull()
  })

  it("adds to the look in progress by naming the group it grows from", async () => {
    setCurrentQuery("c1", { id: "g1", count: 3 })
    const create = vi.spyOn(relationAPI, "create").mockResolvedValue({ group: { id: "g2", member_count: 4, left_out: 0 }, run: null })
    wrap(<Routes><Route path="/" element={<LookIntoButton caseId="c1" surface="financial" items={[{ target_type: "financial_transaction", target_id: "p1" }]} />} />
      <Route path="/cases/c1/relations/g2" element={<p>result page</p>} /></Routes>)
    fireEvent.click(screen.getByRole("button", { name: "Corroborate" }))
    fireEvent.click(screen.getByRole("button", { name: /Add to the look in progress \(3 items\)/ }))
    await waitFor(() => expect(create).toHaveBeenCalledWith("c1", expect.objectContaining({ extends: "g1", members: [{ type: "financial_transaction", id: "p1" }] })))
    await screen.findByText("result page")
    expect(currentQuery("c1")).toEqual({ id: "g2", count: 4 })
  })
})

describe("the result page", () => {
  it("says what it is doing with true numbers while the run works", async () => {
    vi.spyOn(relationAPI, "get").mockResolvedValue({ group: { id: "g", member_count: 5, left_out: 0, members: [], created_at: "" }, run: { id: "r", selection_id: "g", status: "running", step: "Counting how often these kinds of record occur (1 of 1)", progress: {}, error: null, hypotheses: null } })
    wrap(<Routes><Route path="/cases/:id/relations/:selectionId" element={<RelationsPage />} /></Routes>, "/cases/c1/relations/g")
    expect(await screen.findByText(/Counting how often these kinds of record occur \(1 of 1\)/)).toBeTruthy()
    expect(screen.getByText(/Working on 5 items/)).toBeTruthy()
  })

  it("shows candidates graded, the pairs with no link with their search, and a model reading as one", async () => {
    vi.spyOn(relationAPI, "get").mockResolvedValue({
      group: { id: "g", member_count: 2, left_out: 0, members: [], created_at: "" },
      run: { id: "r", selection_id: "g", status: "done", step: "Done", progress: {}, error: null, result,
        hypotheses: { model: "stub-model", status: "A model reading. No person has confirmed it.", no_links: "", items: [
          { id: 0, kind: "coincidence", statement: "Chance.", predicts: "", for: [], against: [{ cite: "rec://x", text: "t" }], distinguishing_record: "a third phone", search: "all phones: none", accepted: null }] } },
    })
    wrap(<Routes><Route path="/cases/:id/relations/:selectionId" element={<RelationsPage />} /></Routes>, "/cases/c1/relations/g")
    expect(await screen.findByText(/1 candidate links \(1 strong/)).toBeTruthy()
    expect(screen.getByText("Both carry the same name.")).toBeTruthy()
    expect(screen.getAllByText(/not proof that no link exists/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Searched: dates of both/)).toBeTruthy()
    expect(screen.getByText(/A model reading by stub-model/)).toBeTruthy()
    expect((screen.getByRole("button", { name: "Accept as supports" }) as HTMLButtonElement).disabled).toBe(true)
  })
})


describe("a long result", () => {
  it("says how many of how many are shown and reads the next page on request", async () => {
    const big: RelationResult = { ...result, paging: { candidates: { total: 130, shown: 1 }, no_links: { total: 1, shown: 1 }, page: 100 }, counts: { ...result.counts, candidates: 130 } }
    vi.spyOn(relationAPI, "get").mockResolvedValue({ group: { id: "g", member_count: 2, left_out: 0, members: [], created_at: "" },
      run: { id: "r", selection_id: "g", status: "done", step: "Done", progress: {}, error: null, result: big, hypotheses: null } })
    const rows = vi.spyOn(relationAPI, "rows").mockResolvedValue({ total: 130, returned: 1, next_offset: null,
      rows: [{ ...result.candidates[0], reasons: ["The next page row."] }] } as never)
    wrap(<Routes><Route path="/cases/:id/relations/:selectionId" element={<RelationsPage />} /></Routes>, "/cases/c1/relations/g")
    expect(await screen.findByText("Showing 1 of 130.")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Show more" }))
    expect(await screen.findByText("The next page row.")).toBeTruthy()
    expect(rows).toHaveBeenCalledWith("c1", "r", "candidates", 1)
  })
})


describe("beside Add to… on the phone, passage and search screens", () => {
  const links = [{ target_type: "phone_record" as const, target_id: "r1", label: "Call", source_anchor: {} },
    { target_type: "evidence_passage" as const, target_id: "f:h:1:9", source_anchor: {} }]
  const menu = <AddToMenu caseId="c1" links={links} noun="records" targets={[]} client={{} as never} origin="Added from Conversations" keys={false} />
  it("offers the look in a router, and none where it could not open", async () => {
    wrap(menu)
    expect(await screen.findByRole("button", { name: "Corroborate" })).toBeTruthy()
    plainRender(menu)
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getAllByRole("button", { name: "Corroborate" }).length).toBe(1)
  })
  it("is not offered when nothing is selected", () => {
    wrap(<AddToMenu caseId="c1" links={[]} noun="records" targets={[]} client={{} as never} origin="x" keys={false} />)
    expect(screen.queryByRole("button", { name: "Corroborate" })).toBeNull()
  })
})
