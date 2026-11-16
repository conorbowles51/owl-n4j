import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/features/phones/api", async (orig) => ({
  ...(await orig<object>()),
  getPhones: vi.fn().mockResolvedValue({ case_id: "c", total: 3, phones: [{ extraction_id: "e1", label: "C1" }, { extraction_id: "e2", label: "C2" }, { extraction_id: "e3", label: "C3" }], case_zone: { name: "UTC", basis: "default", note: null } }),
}))
vi.mock("@/features/pattern/api", async (orig) => ({ ...(await orig<object>()), patternAPI: { keyDates: vi.fn().mockResolvedValue({ items: [] }) } }))
import { ApproachLayout } from "./ApproachLayout"

const run = { id: "r1", status: "completed", finished_at: "2023-03-14T09:00:00Z", counts: { by_kind: { a: 9 } }, coverage: { sentence: "Read 3 phones." }, progress: {} }
const results = vi.fn()
const client = {
  approach: "x", runs: vi.fn().mockResolvedValue({ items: [run] }), coverage: vi.fn().mockResolvedValue({ sentence: "s" }),
  request: vi.fn(), cancel: vi.fn(), run: vi.fn(), results, detail: vi.fn(), keep: vi.fn(), decide: vi.fn(),
} as never

const page = (at: string, pair = false) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="/cases/:id/x" element={<ApproachLayout caseId="c" title="T" whatItDoes="w" client={client} queryKey="x" tabs={[{ kind: "a", label: "A" }]} words={() => ({ title: "t" })}
          collectLabel={() => "l"} origin="o" testId="t" pairByDesign={pair} />} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>,
)

beforeEach(() => {
  localStorage.clear()
  results.mockReset().mockResolvedValue({ total: 4, offset: 0, limit: 100, items: [] })
})

describe("analysis pages: phone layers", () => {
  it("asks only for the phones that are on, and drops the every-phone tab numbers while one is off", async () => {
    localStorage.setItem("loupe.phone_layers", "on")
    page("/cases/c/x?phones=e1,e2")
    const group = await screen.findByRole("group", { name: "Phone layers" })
    expect(within(group).getByLabelText("C3 on")).not.toBeChecked()
    await waitFor(() => expect(results).toHaveBeenCalledWith("c", "r1", expect.objectContaining({ phones: ["e1", "e2"] })))
    expect(screen.getByRole("tab", { name: "A" })).toBeTruthy()
    fireEvent.click(within(group).getByLabelText("C1 on"))
    await waitFor(() => expect(results).toHaveBeenLastCalledWith("c", "r1", expect.objectContaining({ phones: ["e2"] })))
  })
  it("asks for every phone (no phones sent) with all on", async () => {
    localStorage.setItem("loupe.phone_layers", "on")
    page("/cases/c/x")
    await screen.findByRole("group", { name: "Phone layers" })
    await waitFor(() => expect(results).toHaveBeenCalledWith("c", "r1", expect.objectContaining({ phones: [] })))
    expect(screen.getByRole("tab", { name: "A (9)" })).toBeTruthy()
  })
  it("a page that compares two phones by design shows no layers", async () => {
    localStorage.setItem("loupe.phone_layers", "on")
    page("/cases/c/x", true)
    await waitFor(() => expect(results).toHaveBeenCalled())
    expect(screen.queryByRole("group", { name: "Phone layers" })).toBeNull()
  })
})
