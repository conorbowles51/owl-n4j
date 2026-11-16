vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/cases/members-api", () => ({ caseMembersAPI: { getMyMembership: vi.fn().mockResolvedValue({ permissions: { case: { edit: true } } }) } }))
vi.mock("@/features/phones/api", async (orig) => ({
  ...(await orig<object>()),
  getPhones: vi.fn().mockResolvedValue({ case_id: "c", total: 2, phones: [{ extraction_id: "e1", label: "Phone 1" }, { extraction_id: "e2", label: "Phone 2" }], case_zone: { name: "UTC", basis: "default", note: null } }),
}))
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import MonitoringAppsPage from "./MonitoringAppsPage"

const data = {
  label: "Indicator, not a finding", limits: "It does not show who installed it.", total: 2, monitoring_apps: 1, bank_control_notices: 1, outside_dates: 3,
  coverage: "Compared 12 apps.", not_read: "A statement does not print these events.", set_aside: [],
  items: [
    { kind: "monitoring_app", rec: "rec://1", phone: "Phone 1", at: null, label: "Indicator, not a finding", identifier: "com.apspy.app", listed_as: "TheTruthSpy", basis: "On the public list; no person has reviewed this entry.", name_on_phone: "System Service" },
    { kind: "bank_control", rec: "rec://2", phone: "Phone 1", at: "2023-05-01T09:00:00+00:00", label: "The words of a notice on the phone, not a finding", notice: "a new payee", institution: "Synthetic Bank" },
  ],
  list_summary: { version: "v1", apps: 130, identifiers: 618, edits: [], source: { name: "Echap stalkerware-indicators", url: "https://example.test", license: "CC-BY 4.0", commit: "abc", retrieved_on: "2026-11-05", note: "No person has reviewed these entries." } },
}

function show(entry = "/cases/c/phone-analyses/monitoring-apps", withData = data) {
  vi.mocked(fetchAPI).mockResolvedValue(withData as never)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes><Route path="/cases/:id/phone-analyses/monitoring-apps" element={<MonitoringAppsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

it("shows each item as an indicator with its basis, beside the bank notices", async () => {
  show()
  expect((await screen.findByTestId("monitoring-counts")).textContent).toContain("Indicator, not a finding: 1 listed app, 1 bank notice. 3 more fall outside these dates.")
  expect(screen.getByTestId("monitoring-basis").textContent).toContain("no person has reviewed")
  expect(screen.getByTestId("monitoring-limits").textContent).toContain("who installed it")
  expect(screen.getAllByTestId("monitoring-item").map((x) => x.getAttribute("data-kind"))).toEqual(["monitoring_app", "bank_control"])
})

it("names the list's source and offers the edit to someone who can", async () => {
  show()
  expect((await screen.findByTestId("monitoring-source")).textContent).toContain("130 apps, 618 identifiers")
  expect(await screen.findByRole("button", { name: "Save" })).toBeDisabled()
})

it("phone layers: a phone off drops its items, says how many of how many it shows, and each phone states its own count", async () => {
  localStorage.setItem("loupe.phone_layers", "on")
  const two = { ...data, items: [data.items[0], { ...data.items[1], phone: "Phone 2" }] }
  show("/cases/c/phone-analyses/monitoring-apps?phones=e1,e2", two)
  const group = await screen.findByRole("group", { name: "Phone layers" })
  await waitFor(() => expect(within(group).getAllByText("1 item")).toHaveLength(2))
  expect(screen.getAllByTestId("monitoring-item")).toHaveLength(2)
  fireEvent.click(within(group).getByLabelText("Phone 2 on"))
  await waitFor(() => expect(screen.getAllByTestId("monitoring-item")).toHaveLength(1))
  expect(screen.getByText(/Showing 1 of 2 items; the counts above are for every phone/)).toBeTruthy()
  localStorage.clear()
})
