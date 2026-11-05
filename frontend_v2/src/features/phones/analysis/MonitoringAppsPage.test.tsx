vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/cases/members-api", () => ({ caseMembersAPI: { getMyMembership: vi.fn().mockResolvedValue({ permissions: { case: { edit: true } } }) } }))
import { render, screen } from "@testing-library/react"
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

function show() {
  vi.mocked(fetchAPI).mockResolvedValue(data as never)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c/phone-analyses/monitoring-apps"]}>
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
