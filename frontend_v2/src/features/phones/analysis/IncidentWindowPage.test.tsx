import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 16 (approach 13) and J-5c entries. Invented data only. */
const pattern = vi.hoisted(() => ({ subjects: vi.fn() }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: pattern }))
vi.mock("@/features/pattern/components/WindowPanel", () => ({
  WindowPanel: (p: { at: string; day?: string | null; range?: { start: string; end: string } | null; zone?: string }) => (
    <div data-testid="window">{JSON.stringify({ at: p.at, day: p.day ?? null, range: p.range ?? null, zone: p.zone })}</div>),
}))

import IncidentWindowPage, { WHAT_IT_DOES } from "./IncidentWindowPage"

function mount(path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><Routes><Route path="/cases/:id/w" element={<IncidentWindowPage />} /></Routes></MemoryRouter>
    </QueryClientProvider>)
}
const shown = async () => JSON.parse((await screen.findByTestId("window")).textContent || "{}")

describe("Incident window (05 16, J-5c)", () => {
  it("opens from a statement with the statement's own window and zone", async () => {
    mount("/cases/c1/w?start=2023-05-01T09:00:00Z&end=2023-05-01T13:00:00Z&zone=Europe/London&label=the%20statement")
    expect(await shown()).toEqual({ at: "2023-05-01T09:00:00Z", day: null, range: { start: "2023-05-01T09:00:00Z", end: "2023-05-01T13:00:00Z" }, zone: "Europe/London" })
    expect(screen.getByText(/Around the window of the statement \(zone: Europe\/London\)\./)).toBeInTheDocument()
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(pattern.subjects).not.toHaveBeenCalled()
  })

  it("opens from a record or key date at its moment", async () => {
    mount("/cases/c1/w?at=2023-05-01T10:15:00Z&label=the%20selected%20message%20or%20call")
    expect((await shown()).at).toBe("2023-05-01T10:15:00Z")
    expect(screen.getByText("Around the selected message or call.")).toBeInTheDocument()
  })

  it("with no moment chosen, says it shows the latest moment on the phones, and opens a typed moment", async () => {
    pattern.subjects.mockResolvedValue({ extractions: [{ last: "2023-05-02T08:00:00Z" }, { last: "2023-06-01T08:00:00Z" }], total_extractions: 2 })
    mount("/cases/c1/w")
    expect((await shown()).at).toBe("2023-06-01T08:00:00Z")
    expect(screen.getByText("Around the latest moment on the case's phones (no moment chosen yet).")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Moment/), { target: { value: "2023-05-01T10:00" } })
    fireEvent.click(screen.getByRole("button", { name: "Open the window" }))
    expect(await screen.findByText("Around the typed moment.")).toBeInTheDocument()
  })
})
