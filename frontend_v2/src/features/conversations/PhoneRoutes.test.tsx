import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { PhonesIndexPage } from "./PhoneRoutes"

const mocks = vi.hoisted(() => ({ phones: vi.fn() }))
vi.mock("@/features/phones/api", () => ({ getPhones: mocks.phones, getRecord: vi.fn(), failureText: (_e: unknown, w: string) => w }))
vi.mock("@/features/phones/components/ComparePhones", () => ({ ComparePhones: () => null }))

const phone = (id: string, label: string, standing: string) => ({
  extraction_id: id, label, standing, device: { manufacturer: null, model: null },
  counts: { messages: 1, calls: 0, locations: 0 },
})

describe("Phones list after a Replace (07 J-13b, 01 10.7)", () => {
  it("lists a retired report apart, so two reports of one phone never share a link name", async () => {
    mocks.phones.mockResolvedValue({ phones: [phone("n", "C1", "active"), phone("b", "C2", "active"), phone("o", "C1", "superseded")], total: 3 })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/case-1/phones"]}>
          <Routes>
            <Route path="/cases/:id/phones" element={<PhonesIndexPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole("link", { name: /^C1$/ })).toHaveAttribute("href", "/cases/case-1/phones/n")
    const replaced = screen.getByRole("region", { name: "Replaced reports" })
    expect(replaced).toHaveTextContent("Replaced report: C1")
    expect(screen.getAllByRole("link", { name: /^C1\b/ })).toHaveLength(1) // the journeys open a phone by its name
    expect(screen.getByRole("link", { name: "Replaced report: C1" })).toHaveAttribute("href", "/cases/case-1/phones/o")
  })
})
