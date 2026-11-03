vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { AgentProposalsPanel } from "./AgentProposalsPanel"
import { alertAmount } from "../agent-proposals"

const lead = {
  id: "o-1",
  case_id: "case-a",
  output_type: "lead_card",
  review_status: "pending_review",
  created_at: "2026-11-03T10:00:00Z",
  content: {
    institution: "BBVA México",
    account_ending: "ending 4821",
    request_period: { start: "2024-01-15", end: "2024-03-02" },
    counts: { transactional: 2, account: 1 },
    alerts: [
      { cite: "rec://r-1", evidence_class: "transactional", at: "2024-01-15T09:30:00+00:00", amount_minor: 250000, currency: "MXN", direction: "credit" },
      { cite: "rec://r-2", evidence_class: "transactional", at: "2024-03-02T10:00:00+00:00", amount_minor: 150000, currency: "MXN", direction: "debit" },
    ],
    alerts_total: 2,
    citations: ["rec://r-1", "rec://r-2"],
  },
  citations: [
    { cite: "rec://r-1", label: "Phone record" },
    { cite: "rec://r-2", label: "Phone record" },
  ],
  proposal: { kind: "lead_card", model: "DeepSeek V4 Pro", for_name: "Verification user" },
}

it("a lead card lists each alert without a total, and is accepted only after a source is opened and a due date set", async () => {
  const api = vi.mocked(fetchAPI)
  api.mockImplementation(async (url: string) => {
    if (url.includes("/opened")) return { opened: ["rec://r-1"] }
    if (url.includes("/accept")) return { ...lead, review_status: "accepted" }
    return { items: [lead], total: 1, returned: 1, limit: 50, offset: 0 }
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AgentProposalsPanel caseId="case-a" canEdit />
    </QueryClientProvider>
  )
  expect(await screen.findByText(/BBVA México · ending 4821/)).toBeVisible()
  expect(screen.getByText(/2024-01-15 to 2024-03-02/)).toBeVisible()
  expect(screen.getByText(/MX\$2,500.00/)).toBeVisible()
  expect(screen.queryByText(/4,000/)).toBeNull()
  const accept = screen.getByTestId("proposal-accept")
  expect(accept).toBeDisabled()
  fireEvent.click(screen.getAllByTestId("proposal-open-source")[0])
  await screen.findByText("✓ opened")
  expect(accept).toBeDisabled() // no due date yet
  fireEvent.change(screen.getByLabelText("Task due"), { target: { value: "2026-11-10" } })
  expect(accept).toBeEnabled()
  fireEvent.click(accept)
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/workspace/case-a/proposals/o-1/accept", {
      method: "POST",
      body: { due_at: "2026-11-10", via: "ui" },
    })
  )
})

it("formats an alert amount in its own currency's minor unit", () => {
  expect(alertAmount({ amount_minor: 1500, currency: "JPY" })).toBe("¥1,500")
  expect(alertAmount({ amount_minor: null, currency: "MXN" })).toBeNull()
})
