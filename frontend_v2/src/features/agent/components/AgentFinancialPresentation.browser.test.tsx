import "@/styles/globals.css"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { page, userEvent } from "vitest/browser"
import { afterEach, expect, it, vi } from "vitest"
import { AgentPage } from "./AgentPage"
import { agentAPI } from "../api"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import type { AgentThreadDetail } from "../types"

vi.mock("../api", () => ({
  agentAPI: {
    listThreads: vi.fn(),
    getThread: vi.fn(),
    artifactExportUrl: () => "/synthetic-export",
  },
}))
vi.mock("@/features/workspace/hooks/use-workspace", () => ({
  useCaseContext: () => ({ data: { active_mandate: null } }),
}))
vi.mock("@/features/workspace/api", () => ({
  workspaceAPI: {
    getCaseContext: async () => ({ active_mandate: null }),
    listMandateVersions: async () => [],
  },
}))
vi.mock("@/features/settings/components/ActiveAIModel", () => ({
  ActiveAIModel: () => <span>Synthetic model</span>,
}))

const caseId = "11111111-1111-4111-8111-111111111111"
const source = `/cases/${caseId}/financial?view=statements&files=1&reviewFile=22222222-2222-4222-8222-222222222222`
const notes =
  "Working imported payments, January–March 2026. Two account summary rows cover all 130 matching payments: 90 EUR bank payments and 40 USD card postings. Currency and account-type amounts remain separate. Unprocessed source documents and incomplete records are outside these totals."
const chartNotes =
  "EUR bank payments only: 90 matching payments across two recorded months, January and March. February is not represented. USD card postings are outside this chart scope; no missing-month activity has been invented."
const thread: AgentThreadDetail = {
  id: "synthetic-thread",
  case_id: caseId,
  title: "Synthetic full financial analysis",
  status: "completed",
  owner_user_id: "synthetic-user",
  message_count: 1,
  created_at: "2026-09-25T12:00:00Z",
  updated_at: "2026-09-25T12:00:00Z",
  last_message_at: "2026-09-25T12:00:00Z",
  messages: [
    {
      id: "synthetic-message",
      role: "assistant",
      content: `The report covers saved imported payments. [Example statement, January](${source}).`,
      artifact_ids: [],
      created_at: "2026-09-25T12:00:00Z",
      tool_trace_summary: [
        {
          id: "coverage",
          name: "get_financial_coverage",
          arguments: {},
          status: "success",
          duration_ms: 5,
          summary: "Some source work remains outside the imported ledger.",
        },
      ],
    },
  ],
  artifacts: [
    {
      id: "table",
      type: "table",
      title: "Ledger account totals",
      metadata: { notes },
      data: {
        columns: [
          { key: "currency", label: "Currency" },
          { key: "account_type", label: "Account type" },
          { key: "count", label: "Matching payments" },
        ],
        rows: [
          { currency: "EUR", account_type: "bank", count: 90 },
          { currency: "USD", account_type: "credit_card", count: 40 },
        ],
      },
    },
    {
      id: "chart",
      type: "chart",
      title: "Recorded EUR bank months",
      metadata: {},
      data: {
        chart_type: "bar",
        notes: chartNotes,
        x_key: "month",
        y_keys: ["payment_count"],
        rows: [
          { month: "2026-01", payment_count: 55 },
          { month: "2026-03", payment_count: 35 },
        ],
      },
    },
    {
      id: "report",
      type: "report",
      title: "Financial investigation report",
      metadata: {},
      data: {
        purpose: "Review available imported payments",
        scope: notes,
        included_items: ["Coverage", "Account summaries", "Sources"],
        sections: [
          {
            heading: "Coverage and sources",
            content: `Only imported payments in the stated population were analysed. [Example statement, January](${source}).`,
          },
        ],
        open_questions: [
          "Review incomplete records separately before making completeness claims.",
        ],
      },
    },
  ],
}
afterEach(cleanup)

it("opens saved ledger analysis with visible coverage, readable progress, separate chart months and source links through artifact return", async () => {
  localStorage.setItem("owl.agent.showInvestigationTrail", "true")
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useUIStore.setState({ graphPanelCollapsed: true })
  vi.mocked(agentAPI.listThreads).mockResolvedValue([thread])
  vi.mocked(agentAPI.getThread).mockResolvedValue(thread)
  await page.viewport(1440, 950)
  render(
    <MemoryRouter initialEntries={[`/cases/${caseId}/agent`]}>
      <Routes>
        <Route
          path="/cases/:id/agent"
          element={
            <div className="h-screen">
              <AgentPage />
            </div>
          }
        />
      </Routes>
    </MemoryRouter>
  )
  await screen.findByRole("button", {
    name: /Synthetic full financial analysis/,
  })
  await page
    .getByRole("button", { name: /Synthetic full financial analysis/ })
    .click()
  const region = () =>
    screen.getByRole("region", { name: "Analysis scope and notes" })
  await waitFor(() => expect(region()).toHaveTextContent(notes))
  await page.getByRole("button", { name: /Investigation trail/ }).click()
  expect(screen.getByText("Checked financial coverage")).toBeVisible()
  expect(
    screen.getByText("Some source work remains outside the imported ledger.")
  ).toBeVisible()
  expect(
    screen.getByRole("columnheader", { name: "Account type" })
  ).toBeVisible()
  expect(
    screen.getByRole("link", { name: "Example statement, January" })
  ).toHaveAttribute("href", source)
  expect(
    screen.getByRole("link", { name: "Example statement, January" })
  ).toHaveAttribute("rel", "noopener noreferrer")
  await page.getByRole("button", { name: /Recorded EUR bank months/ }).click()
  expect(region()).toHaveTextContent(chartNotes)
  await screen.findByText("2026-01")
  expect(
    screen.getAllByText(/^2026-\d{2}$/).map((node) => node.textContent)
  ).toEqual(["2026-01", "2026-03"])
  expect(screen.queryByText("2026-02")).toBeNull()
  await page
    .getByRole("button", { name: /Financial investigation report/ })
    .click()
  expect(
    screen.getByRole("heading", { name: "Coverage and sources" })
  ).toBeVisible()
  expect(
    screen.getAllByRole("link", { name: "Example statement, January" })
  ).toHaveLength(2)
  await page.getByRole("button", { name: /Ledger account totals/ }).click()
  expect(region()).toHaveTextContent(notes)
  await page.screenshot({
    path: "/private/tmp/loupe-agent-ledger-notes-wide.png",
    element: region(),
  })
  await page.viewport(390, 844)
  expect(region()).toBeVisible()
  expect(region().scrollWidth).toBeLessThanOrEqual(region().clientWidth + 1)
  region().focus()
  expect(region()).toHaveFocus()
  await userEvent.keyboard("{End}")
  await waitFor(() => {
    expect(region().scrollTop).toBeGreaterThan(0)
    expect(
      region().querySelector("p")!.getBoundingClientRect().bottom
    ).toBeLessThanOrEqual(region().getBoundingClientRect().bottom + 1)
  })
  await page.screenshot({
    path: "/private/tmp/loupe-agent-ledger-notes-narrow.png",
    element: region(),
  })
  expect(agentAPI.getThread).toHaveBeenCalledOnce()
}, 20000)
