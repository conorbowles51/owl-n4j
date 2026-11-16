import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"

vi.mock("@/features/phones/api", async (orig) => ({
  ...(await orig<object>()),
  getPhones: vi.fn().mockResolvedValue({ case_id: "c", total: 2, phones: [{ extraction_id: "e1", label: "C1" }, { extraction_id: "e2", label: "C2" }], case_zone: { name: "UTC", basis: "default", note: null } }),
}))
import { AddOtherPhones } from "./AddOtherPhones"

const show = (entry: string) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[entry]}><AddOtherPhones caseId="c" extraction="e1" /></MemoryRouter>
  </QueryClientProvider>)

beforeEach(() => localStorage.clear())

it("leads to the case-level views with this phone on and this page's filters carried", async () => {
  localStorage.setItem("loupe.phone_layers", "on")
  show("/cases/c/phones/e1/records/calls?from=2024-01-01&record=r9")
  const link = await screen.findByRole("link", { name: "Conversations" })
  expect(link.getAttribute("href")).toBe("/cases/c/conversations?from=2024-01-01&phones=e1")
  expect(screen.getByRole("link", { name: "Map" }).getAttribute("href")).toContain("phones=e1")
})

it("shows nothing while the phone_layers setting is off", async () => {
  show("/cases/c/phones/e1")
  await new Promise((r) => setTimeout(r, 50))
  expect(screen.queryByTestId("add-other-phones")).toBeNull()
})
