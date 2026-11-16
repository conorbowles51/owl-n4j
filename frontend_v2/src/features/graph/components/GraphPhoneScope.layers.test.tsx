import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"

vi.mock("@/features/phones/api", async (orig) => ({
  ...(await orig<object>()),
  getPhones: vi.fn().mockResolvedValue({ case_id: "c", total: 3, phones: [{ extraction_id: "e1", label: "C1" }, { extraction_id: "e2", label: "C2" }, { extraction_id: "e3", label: "C3" }], case_zone: { name: "UTC", basis: "default", note: null } }),
  getSettings: vi.fn().mockResolvedValue({ effective: { name: "UTC" } }),
}))
vi.mock("@/features/phones/people.api", () => ({ peopleAPI: { scopePresets: vi.fn().mockResolvedValue({ people: [] }), scopeIdentities: vi.fn().mockResolvedValue({ total: 0 }) } }))
import { GraphPhoneScope } from "./GraphPhoneScope"

function Where() { const l = useLocation(); return <p data-testid="where">{l.search}</p> }

beforeEach(() => localStorage.clear())

it("lists every phone on the Graph's phone scope and a switch changes the phones in the address", async () => {
  localStorage.setItem("loupe.phone_layers", "on")
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c/graph?scope=phones&phones=e1,e2"]}>
        <GraphPhoneScope caseId="c" nodes={[]} edges={[]} />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const group = await screen.findByRole("group", { name: "Phone layers" })
  expect(within(group).getByLabelText("C3 on")).not.toBeChecked()
  fireEvent.click(within(group).getByLabelText("C2 on"))
  await waitFor(() => expect(screen.getByTestId("where").textContent).toContain("phones=e1"))
  expect(screen.getByTestId("where").textContent).not.toContain("e2")
})
