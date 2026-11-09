import { act, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "@/features/financial/stores/financial-drafts"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { Step } from "../api"
import { trailGroup } from "./trail"
import { decide, FIND_MS, returnTo, useHistory, useReturnCheck } from "./recorder"
import { mergesInto, rangeWords, stepName, type Snapshot } from "./view-state"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mocked(fetchAPI)

const snap = (over: Partial<Snapshot> = {}): Snapshot => ({
  screen: "financial", path: "/cases/c1/financial?view=transactions", state: {}, item: null, name: "Transactions", ...over,
})

describe("step names", () => {
  const label = (id: string) => ({ "acct-1": "BBVA 0110280038", "person:jose": "Jose Alejandro Reyes Zeind", f6: "x.pdf" } as Record<string, string>)[id] ?? null
  it("are plain words from what is on screen", () => {
    expect(stepName({ pathname: "/cases/c1/financial", search: "?view=transactions", label, state: { financial: { drafts: {}, scope: { accountId: "acct-1", startDate: "2022-11-01", endDate: "2022-11-30" } } } }))
      .toBe("Transactions · BBVA 0110280038 · Nov 2022")
    expect(stepName({ pathname: "/cases/c1/graph", search: "", label, state: { graph: { selected: ["person:jose"], search: "", mode: "filter", types: null, hidden: [], subgraph: [] } } }))
      .toBe("Graph · Jose Alejandro Reyes Zeind")
    expect(stepName({ pathname: "/cases/c1/financial", search: "?view=statements", label, state: { document: { evidenceId: "f6", name: "11 ARRENDO BBVA USD NOV 2022.pdf", page: 2, pages: 6 } } }))
      .toBe("Statement page 2 of 6 · 11 ARRENDO BBVA USD NOV 2022.pdf")
    expect(stepName({ pathname: "/cases/c1/evidence", search: "?file=f6", label, state: {} })).toBe("Evidence · x.pdf")
    expect(rangeWords("2022-11-01", "2023-02-28")).toBe("Nov 2022 to Feb 2023")
  })
})

describe("merging tiny changes", () => {
  it("scrolling, a panel or typing in a filter merge; a new screen, item or applied filter is a new step", () => {
    const base = snap({ state: { financial: { drafts: { t: { search: "a" } }, scope: {} } } })
    expect(mergesInto(base, { ...base, state: { ...base.state, scrollKey: "tx-40" } }, 60_000)).toBe(true)
    const typed = snap({ state: { financial: { drafts: { t: { search: "arren" } }, scope: {} } } })
    expect(mergesInto(base, typed, 800)).toBe(true)
    expect(mergesInto(base, typed, 10_000)).toBe(false) // typed long after: a filter applied
    expect(mergesInto(base, snap({ screen: "graph", path: "/cases/c1/graph" }), 100)).toBe(false)
    expect(mergesInto(base, { ...base, item: { kind: "financial_transaction", id: "tx-9" } }, 100)).toBe(false)
    const filtered = snap({ state: { financial: { drafts: { t: { search: "a", direction: "out" } }, scope: {} } } })
    expect(mergesInto(base, filtered, 100)).toBe(false)
  })
  it("the recorder rewrites only a step it wrote, and skips a view it already holds", () => {
    const last = { snapshot: snap(), id: "s1", at: 0, returned: false }
    expect(decide(last, snap(), 10)).toBe("skip")
    expect(decide(last, snap({ state: { scrollKey: "tx-2" } }), 10)).toBe("merge")
    expect(decide({ ...last, returned: true }, snap({ state: { scrollKey: "tx-2" } }), 10)).toBe("local")
    expect(decide(last, snap({ screen: "graph", path: "/cases/c1/graph" }), 10)).toBe("new")
    expect(decide(null, snap(), 10)).toBe("new")
  })
})

function Harness({ step }: { step: Step }) {
  useReturnCheck("c1")
  const navigate = useNavigate()
  const l = useLocation()
  return (
    <>
      <button onClick={() => returnTo("c1", step, navigate)}>Go back</button>
      <p data-testid="where">{l.pathname + l.search}</p>
      {l.pathname.endsWith("/financial") && (
        <main>
          {["tx-1", "tx-2", "tx-3"].map((k) => (
            <div key={k} data-row-key={k}>{k}</div>
          ))}
        </main>
      )}
    </>
  )
}

function mount(step: Step) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cases/c1/graph"]}>
        <Routes>
          <Route path="/cases/:id/*" element={<Harness step={step} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const paymentStep = (over: Partial<Step> = {}): Step => ({
  id: "s2", at: "2026-11-09T10:00:00Z", name: "Transactions · BBVA 0110280038", screen: "financial",
  path: "/cases/c1/financial?view=transactions&payment=tx-2",
  state: { scrollKey: "tx-2", financial: { drafts: { "payment-table:x": { search: "ARRENDO", direction: "out", sort: "amount" } }, scope: { accountId: "acct-1" } } },
  item: { kind: "financial_transaction", id: "tx-2", label: "ARRENDO" },
  ...over,
})

describe("returning to a step", () => {
  beforeEach(() => {
    useAuthStore.setState({ user: { id: "u1", username: "u1" } } as never)
    useFinancialDraftStore.setState({ drafts: {} })
    useHistory.setState({ currentId: null, last: null, returning: null, message: null })
    Element.prototype.scrollIntoView = vi.fn()
  })
  afterEach(() => vi.useRealTimers())

  it("restores a payment with its filters, sort and scroll position", async () => {
    mount(paymentStep())
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Go back" })))
    expect(screen.getByTestId("where").textContent).toBe("/cases/c1/financial?view=transactions&payment=tx-2")
    expect(useFinancialDraftStore.getState().drafts["u1:c1:payment-table:x"]).toEqual({ search: "ARRENDO", direction: "out", sort: "amount" })
    const row = document.querySelector('[data-row-key="tx-2"]') as HTMLElement
    await vi.waitFor(() => expect(row.scrollIntoView).toHaveBeenCalledWith({ block: "start" }))
    expect(useHistory.getState().returning).toBeNull()
    expect(useHistory.getState().message).toBeNull()
    expect(useHistory.getState().currentId).toBe("s2")
  })

  it("a deleted or merged item says so plainly and stays on the nearest view", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mount(paymentStep({ state: { scrollKey: "tx-gone" }, item: { kind: "financial_transaction", id: "tx-gone", label: "ARRENDO NOV" } }))
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Go back" })))
    await act(async () => void vi.advanceTimersByTime(FIND_MS + 500))
    expect(useHistory.getState().message).toBe(
      '"ARRENDO NOV" is not in the case any more: it may have been deleted or merged. This is the nearest view: Financial, with the same filters.'
    )
    expect(screen.getByTestId("where").textContent).toBe("/cases/c1/financial?view=transactions&payment=tx-2")
  })
})

describe("adding a run of steps to a theory", () => {
  it("keeps each step's address and view state, oldest first, so each reopens from the theory", () => {
    const steps = [paymentStep({ id: "s4", at: "2026-11-09T10:03:00Z", name: "Graph · Jose" }), paymentStep({ id: "s2" }), paymentStep({ id: "s3", at: "2026-11-09T10:01:00Z", name: "Map" })]
    const g = trailGroup(steps)
    expect(g.group_type).toBe("step_trail")
    expect(g.members.map((m) => m.id)).toEqual(["s2", "s3", "s4"])
    expect((g.how.steps as Step[]).map((s) => s.path)).toEqual(steps.map(() => "/cases/c1/financial?view=transactions&payment=tx-2"))
    expect(g.words).toBe("3 steps, from Transactions · BBVA 0110280038 to Graph · Jose")
  })
})
