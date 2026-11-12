import "@/styles/globals.css"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { page, userEvent } from "vitest/browser"
import { afterEach, expect, it, vi } from "vitest"
import { AgentPage } from "./AgentPage"
import { agentAPI } from "../api"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { useAgentRunStore } from "../stores/agent-run.store"
import type { AgentMessageResponse, AgentStreamEvent, AgentThreadDetail } from "../types"

vi.mock("../api", () => ({
  agentAPI: {
    listThreads: vi.fn(),
    getThread: vi.fn(),
    streamMessage: vi.fn(),
    listWorkflows: vi.fn().mockResolvedValue({ workflows: [], total: 0 }),
    listModels: vi.fn().mockResolvedValue({ choices: [
      { key: "synthetic:high", provider: "synthetic", model_id: "test", model_name: "Synthetic", reasoning: "high", label: "Synthetic model · thinks longer", default: true },
      { key: "synthetic:max", provider: "synthetic", model_id: "test", model_name: "Synthetic", reasoning: "max", label: "Synthetic model · maximum reasoning", default: false },
    ], default: "synthetic:high" }),
    activeRuns: vi.fn().mockResolvedValue({ runs: [] }),
    getCapabilities: vi.fn().mockResolvedValue({ types: [], total: 0, note: "" }),
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
    path: "../../../../../output/playwright/loupe-agent-ledger-notes-wide.png",
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
    path: "../../../../../output/playwright/loupe-agent-ledger-notes-narrow.png",
    element: region(),
  })
  expect(agentAPI.getThread).toHaveBeenCalledOnce()
}, 20000)

it("resumes a saved stopped run without duplicating the question and retains draft issues after settling and reopening", async () => {
  await page.viewport(1440, 950)
  useAgentRunStore.setState({ runsByCase: {} })
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useUIStore.setState({ graphPanelCollapsed: true })
  const question = "Finish my complete synthetic report"
  const pending: AgentThreadDetail = { ...thread, messages: [{ id: "original-question", role: "user", content: question, run_id: "original-run", artifact_ids: [], tool_trace_summary: [], created_at: thread.created_at }], artifacts: [] }
  const draft = { ...thread.artifacts[2], metadata: { validation: { status: "needs_revision", issues: ["Required coverage is missing: source limitations"] } } }
  const complete: AgentThreadDetail = { ...pending, artifacts: [draft], messages: [...pending.messages, { id: "resumed-answer", role: "assistant", content: "Draft saved; source limitations need revision.", run_id: "original-run", artifact_ids: [draft.id], tool_trace_summary: [], created_at: thread.created_at }] }
  vi.mocked(agentAPI.listThreads).mockResolvedValue([pending])
  vi.mocked(agentAPI.getThread).mockReset().mockResolvedValueOnce(pending).mockResolvedValue(complete)
  const response: AgentMessageResponse = { thread_id: pending.id, run_id: "original-run", assistant_message_id: "resumed-answer", answer: complete.messages[1].content, artifacts: [draft], tool_trace: [], model_info: { provider: "synthetic", model_id: "test", model_name: "Synthetic", server: "local" }, status: "needs_revision", created_at: thread.created_at, mandate: { is_stale: false, is_incomplete: true } }
  vi.mocked(agentAPI.streamMessage).mockImplementation(async (_params, onEvent) => {
    onEvent({ type: "run_started", thread_id: pending.id, run_id: "original-run", user_message_id: "original-question", model_info: response.model_info })
    onEvent({ type: "done", response })
  })
  render(<MemoryRouter initialEntries={[`/cases/${caseId}/agent`]}><Routes><Route path="/cases/:id/agent" element={<div className="h-screen"><AgentPage /></div>} /></Routes></MemoryRouter>)
  await screen.findByRole("button", { name: /Synthetic full financial analysis/ })
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  await page.getByRole("button", { name: "Resume run", exact: true }).click()
  await waitFor(() => expect(agentAPI.streamMessage).toHaveBeenCalledWith(expect.objectContaining({ resumeRunId: "original-run", threadId: pending.id }), expect.any(Function)))
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase[caseId]).toBeUndefined())
  expect(screen.getAllByText(question, { exact: true })).toHaveLength(1)
  expect(screen.getByText(/The draft is saved, but checks found issues/)).toBeVisible()
  expect(screen.queryByTestId("agent-run-progress")).not.toBeInTheDocument()
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  expect(await screen.findByText("Required coverage is missing: source limitations")).toBeVisible()
  expect(screen.getByText(/The draft is saved, but checks found issues/)).toBeVisible()
})

it("keeps an older conversation and its exports open while another run streams and completes", async () => {
  await page.viewport(1440, 950)
  useAgentRunStore.setState({ runsByCase: {} })
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useUIStore.setState({ graphPanelCollapsed: true })
  const live: AgentThreadDetail = { ...thread, id: "live-thread", title: "Live research", messages: [], artifacts: [] }
  vi.mocked(agentAPI.listThreads).mockResolvedValue([live, thread])
  vi.mocked(agentAPI.getThread).mockReset().mockImplementation(async (id) => id === live.id ? live : thread)
  const model = { provider: "synthetic", model_id: "test", model_name: "Synthetic", server: "local" }
  let deliver: ((event: AgentStreamEvent) => void) | undefined
  let finish: (() => void) | undefined
  vi.mocked(agentAPI.streamMessage).mockImplementation((_params, onEvent) => new Promise<void>((resolve) => {
    deliver = onEvent; finish = resolve
    onEvent({ type: "run_started", thread_id: live.id, run_id: "background-run", user_message_id: "new-question", model_info: model })
  }))
  render(<MemoryRouter initialEntries={[`/cases/${caseId}/agent`]}><Routes><Route path="/cases/:id/agent" element={<div className="h-screen"><AgentPage /></div>} /></Routes></MemoryRouter>)
  await screen.findByRole("button", { name: /Live research/ })
  await page.getByRole("button", { name: /Live research/ }).click()
  await page.getByRole("textbox", { name: "Agent request" }).fill("Keep researching the synthetic case")
  await page.getByRole("button", { name: "Send agent prompt" }).click()
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase[caseId]?.runId).toBe("background-run"))
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  expect(await screen.findByRole("button", { name: "View running conversation" })).toBeVisible()
  expect(screen.getByRole("button", { name: "XLSX" })).toBeEnabled()
  const background = { ...thread.artifacts[2], id: "new-background-draft", title: "New background draft" }
  await act(async () => { deliver?.({ type: "artifact", artifact: background }); deliver?.({ type: "done", response: { thread_id: live.id, run_id: "background-run", answer: "Background research finished.", artifacts: [background], tool_trace: [], model_info: model, status: "completed", created_at: thread.created_at, mandate: { is_stale: false, is_incomplete: true } } }); finish?.() })
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase[caseId]).toBeUndefined())
  expect(screen.queryByText("Background research finished.")).not.toBeInTheDocument()
  expect(screen.queryByText("New background draft")).not.toBeInTheDocument()
  expect(screen.getByRole("columnheader", { name: "Account type" })).toBeVisible()
  expect(agentAPI.getThread).toHaveBeenCalledTimes(2)
})

it("leaves a cancelled run stopped until the investigator explicitly resumes its saved checkpoint", async () => {
  await page.viewport(1440, 950)
  useAgentRunStore.setState({ runsByCase: {} })
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useUIStore.setState({ graphPanelCollapsed: true })
  const question = "Complete the cancelled synthetic report"
  const pending: AgentThreadDetail = { ...thread, messages: [{ id: "cancelled-question", role: "user", content: question, run_id: "cancelled-run", artifact_ids: [], tool_trace_summary: [], created_at: thread.created_at }], artifacts: [] }
  const complete: AgentThreadDetail = { ...pending, messages: [...pending.messages, { id: "resumed-cancellation", role: "assistant", content: "Explicitly resumed and completed.", run_id: "cancelled-run", artifact_ids: [], tool_trace_summary: [], created_at: thread.created_at }] }
  vi.mocked(agentAPI.listThreads).mockResolvedValue([pending])
  vi.mocked(agentAPI.getThread).mockReset().mockResolvedValueOnce(pending).mockResolvedValue(complete)
  vi.mocked(agentAPI.streamMessage).mockReset().mockImplementation(async (_params, onEvent) => {
    onEvent({ type: "done", response: { thread_id: pending.id, run_id: "cancelled-run", answer: complete.messages[1].content, artifacts: [], tool_trace: [], model_info: { provider: "synthetic", model_id: "test", model_name: "Synthetic", server: "local" }, status: "completed", created_at: thread.created_at, mandate: { is_stale: false, is_incomplete: true } } })
  })
  render(<MemoryRouter initialEntries={[`/cases/${caseId}/agent`]}><Routes><Route path="/cases/:id/agent" element={<div className="h-screen"><AgentPage /></div>} /></Routes></MemoryRouter>)
  await screen.findByRole("button", { name: /Synthetic full financial analysis/ })
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  await act(async () => {
    useAgentRunStore.getState().startRun(caseId, pending.id, question)
    useAgentRunStore.getState().updateRun(caseId, { runId: "cancelled-run" })
    // The cancellation reload still contains the original unanswered question.
    vi.mocked(agentAPI.getThread).mockResolvedValueOnce(pending).mockResolvedValue(complete)
    useAgentRunStore.getState().finishRun(caseId, "cancelled")
  })
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase[caseId]).toBeUndefined())
  expect(agentAPI.streamMessage).not.toHaveBeenCalled()
  await page.getByRole("button", { name: "Resume run", exact: true }).click()
  await waitFor(() => expect(agentAPI.streamMessage).toHaveBeenCalledWith(expect.objectContaining({ resumeRunId: "cancelled-run" }), expect.any(Function)))
  expect(await screen.findByText("Explicitly resumed and completed.")).toBeVisible()
})

it("keeps request, model, send and every export reachable in the normal three-pane layout", async () => {
  await page.viewport(1250, 1280)
  useAgentRunStore.setState({ runsByCase: {} })
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useUIStore.setState({ graphPanelCollapsed: true })
  vi.mocked(agentAPI.listThreads).mockResolvedValue([thread])
  vi.mocked(agentAPI.getThread).mockResolvedValue(thread)
  render(<MemoryRouter initialEntries={[`/cases/${caseId}/agent`]}><Routes><Route path="/cases/:id/agent" element={<div className="h-screen" style={{ width: 1030, marginLeft: 220 }}><AgentPage /></div>} /></Routes></MemoryRouter>)
  await screen.findByRole("button", { name: /Synthetic full financial analysis/ })
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  const request = screen.getByRole("textbox", { name: "Agent request" })
  const conversation = request.closest("section")!
  const workspace = screen.getByRole("region", { name: "Artifact workspace" })
  expect(request.getBoundingClientRect().width).toBeGreaterThan(200)
  expect(screen.getByRole("combobox", { name: "Model for the next message" }).getBoundingClientRect().width).toBeGreaterThan(100)
  expect(screen.getByRole("button", { name: "Send agent prompt" }).getBoundingClientRect().right).toBeLessThanOrEqual(conversation.getBoundingClientRect().right)
  for (const format of ["XLSX", "CSV", "PDF", "Word", "HTML"]) {
    const button = screen.getByRole("button", { name: format })
    expect(button).toBeVisible()
    expect(button.getBoundingClientRect().right).toBeLessThanOrEqual(workspace.getBoundingClientRect().right)
  }
  expect(conversation.scrollWidth).toBeLessThanOrEqual(conversation.clientWidth)
  await page.screenshot({ path: "../../../../../output/playwright/agent-narrow-panes.png" })
})

it("reopens the newest revision of the first report while allowing explicit historical review", async () => {
  await page.viewport(1440, 950)
  useAgentRunStore.setState({ runsByCase: {} })
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useUIStore.setState({ graphPanelCollapsed: true })
  const revisions = [1, 2, 3].map((revision) => ({ ...thread.artifacts[2], id: `report-revision-${revision}`, title: "Versioned synthetic report", metadata: { deliverable_id: "report-family", revision }, data: { sections: [{ id: "analysis", heading: "Analysis", content: `Saved analysis in revision ${revision}.` }] } }))
  const versioned = { ...thread, artifacts: [...revisions, thread.artifacts[0]] }
  vi.mocked(agentAPI.listThreads).mockResolvedValue([versioned])
  vi.mocked(agentAPI.getThread).mockResolvedValue(versioned)
  render(<MemoryRouter initialEntries={[`/cases/${caseId}/agent`]}><Routes><Route path="/cases/:id/agent" element={<div className="h-screen"><AgentPage /></div>} /></Routes></MemoryRouter>)
  await screen.findByRole("button", { name: /Synthetic full financial analysis/ })
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  expect(await screen.findByText("Saved analysis in revision 3.")).toBeVisible()
  expect(screen.getByRole("combobox", { name: "Artifact version" })).toHaveValue("report-revision-3")
  await page.getByRole("combobox", { name: "Artifact version" }).selectOptions("report-revision-1")
  expect(screen.getByText("Saved analysis in revision 1.")).toBeVisible()
  await page.getByRole("button", { name: /Synthetic full financial analysis/ }).click()
  expect(await screen.findByText("Saved analysis in revision 3.")).toBeVisible()
})
