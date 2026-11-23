import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { AgentPage } from "./AgentPage"
import { agentAPI } from "../api"
import type { AgentThreadDetail } from "../types"

// The map's tile worker is a bundler asset the unit project cannot load; the page under test draws no map.
vi.mock("@/features/graph/components/EditNodeDialog", () => ({ EditNodeDialog: () => null }))
vi.mock("@/features/map/components/MapCanvas", () => ({ MapCanvas: () => null }))
vi.mock("@/features/map/components/PlacesMap", () => ({ PlacesMap: () => null }))
vi.mock("@/features/pattern/components/TextPlacePicker", () => ({ TextPlacePicker: () => null }))
vi.mock("../api", () => ({
  agentAPI: {
    listThreads: vi.fn(),
    getThread: vi.fn(),
    streamMessage: vi.fn(),
    listWorkflows: vi.fn().mockResolvedValue({ workflows: [], total: 0 }),
    listModels: vi.fn().mockResolvedValue({ choices: [], default: null }),
    activeRuns: vi.fn().mockResolvedValue({ runs: [] }),
    getCapabilities: vi.fn().mockResolvedValue({ types: [], total: 0, note: "" }),
    artifactExportUrl: () => "/synthetic-export",
  },
}))
vi.mock("@/features/workspace/hooks/use-workspace", () => ({ useCaseContext: () => ({ data: { active_mandate: null } }) }))
vi.mock("@/features/workspace/api", () => ({
  workspaceAPI: { getCaseContext: async () => ({ active_mandate: null }), listMandateVersions: async () => [] },
}))
vi.mock("@/features/settings/components/ActiveAIModel", () => ({ ActiveAIModel: () => <span>Synthetic model</span> }))

const caseId = "11111111-1111-4111-8111-111111111111"
const message = (id: string, content: string) => ({
  id, role: "assistant" as const, content, artifact_ids: [], created_at: "2026-11-15T10:00:00Z", tool_trace_summary: [],
})
const thread: AgentThreadDetail = {
  id: "thread-linked", case_id: caseId, title: "Who paid Ann", status: "completed", owner_user_id: "u",
  message_count: 2, created_at: "2026-11-15T10:00:00Z", updated_at: "2026-11-15T10:00:00Z",
  last_message_at: "2026-11-15T10:00:00Z",
  messages: [message("33333333-3333-4333-8333-333333333331", "An earlier answer."),
             message("33333333-3333-4333-8333-333333333332", "Acme paid Ann three times in January.")],
  artifacts: [],
}

function show(address: string): ReturnType<typeof render> {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const page: ReactNode = (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[address]}>
        <Routes><Route path="/cases/:id/agent" element={<AgentPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
  return render(page)
}

beforeEach(() => {
  vi.mocked(agentAPI.listThreads).mockResolvedValue([thread])
  vi.mocked(agentAPI.getThread).mockReset().mockResolvedValue(thread)
  Element.prototype.scrollIntoView = vi.fn()
  // jsdom has no ResizeObserver; the page's resizable panels need one to mount.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

it("opens the thread and shows the answer a theory links to, from the address alone", async () => {
  const target = thread.messages[1].id
  show(`/cases/${caseId}/agent?thread=${thread.id}&message=${target}`)
  await waitFor(() => expect(agentAPI.getThread).toHaveBeenCalledWith(thread.id))
  expect(await screen.findByText("Acme paid Ann three times in January.")).toBeTruthy()
  const answer = document.getElementById(`agent-message-${target}`)!
  await waitFor(() => expect(answer.scrollIntoView).toHaveBeenCalled())
  expect(answer.getAttribute("aria-current")).toBe("true")
  expect(document.getElementById(`agent-message-${thread.messages[0].id}`)?.getAttribute("aria-current")).toBeNull()
})

it("opens no thread when the address names none", async () => {
  show(`/cases/${caseId}/agent`)
  await waitFor(() => expect(agentAPI.listThreads).toHaveBeenCalled())
  expect(agentAPI.getThread).not.toHaveBeenCalled()
})

it("at phone width shows chat and artifacts one at a time, full width, with no side rail", async () => {
  const realMatchMedia = window.matchMedia
  window.matchMedia = ((query: string) => ({
    matches: query === "(max-width: 767px)", media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  try {
    show(`/cases/${caseId}/agent?thread=${thread.id}`)
    expect(await screen.findByText("Acme paid Ann three times in January.")).toBeTruthy()
    const panes = screen.getByTestId("agent-narrow-panes")
    expect(panes).toBeTruthy()
    expect(screen.queryByTitle("Entity details")).toBeNull()
    expect(screen.queryByRole("button", { name: /expand workspace/i })).toBeNull()
    fireEvent.click(screen.getByRole("tab", { name: /artifacts \(0\)/i }))
    await waitFor(() => expect(screen.queryByText("Acme paid Ann three times in January.")).toBeNull())
    expect(screen.getByRole("tab", { name: /artifacts/i }).getAttribute("aria-selected")).toBe("true")
  } finally {
    window.matchMedia = realMatchMedia
  }
})

it("lets a new thread's guided workflows grow and scroll, so the first ones can be reached", async () => {
  // jsdom has no layout: the box's sizing is what decides it. A centred box fixed at the scroll area's height pushes
  // the top of a taller list (the guided workflows) above the area, out of reach (seen live at 390 and 1440 wide).
  show(`/cases/${caseId}/agent`)
  const empty = await screen.findByTestId("agent-empty")
  expect(empty.className.split(/\s+/)).toContain("min-h-full")
  expect(empty.className.split(/\s+/)).not.toContain("h-full")
})

it("at phone width the thread header has a New thread button that leaves the open thread (followups 23 Nov)", async () => {
  // Below md the thread list (and its New agent thread button) is hidden: a person whose run had opened its thread
  // could not reach the guided workflows or ask a separate question until the run ended.
  const realMatchMedia = window.matchMedia
  window.matchMedia = ((query: string) => ({
    matches: query === "(max-width: 767px)", media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  try {
    show(`/cases/${caseId}/agent?thread=${thread.id}`)
    expect(await screen.findByText("Acme paid Ann three times in January.")).toBeTruthy()
    const listButton = screen.getByRole("button", { name: "New agent thread" })
    expect(listButton.closest("aside")?.className.split(/\s+/)).toContain("hidden")
    const narrow = screen.getByRole("button", { name: "New thread" })
    const classes = narrow.className.split(/\s+/)
    expect(classes).toContain("md:hidden")
    expect(classes).not.toContain("hidden")
    expect(narrow.closest("aside")).toBeNull()
    fireEvent.click(narrow)
    await waitFor(() => expect(screen.queryByText("Acme paid Ann three times in January.")).toBeNull())
    expect(await screen.findByTestId("agent-empty")).toBeTruthy()
  } finally {
    window.matchMedia = realMatchMedia
  }
})
