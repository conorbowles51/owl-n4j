import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { resetAfterFirstPaintForTest } from "@/lib/after-first-paint"
import { resetKeymapForTest } from "@/lib/keymap"

/**
 * Conversations start-up weight (m11052223576567): the four queries the page shell does not need — jobs, my-marks,
 * reader settings, scope presets — wait for the first painted frame. Each test renders to the shell with
 * requestAnimationFrame withheld (no frame painted yet), shows the request was not made, then paints and shows the
 * data still arrives: nothing is lost, only moved after the shell.
 */
const api = vi.hoisted(() => ({
  getPhones: vi.fn(),
  getSettings: vi.fn(),
  getThreads: vi.fn(),
  getParticipants: vi.fn(),
  streamIndex: vi.fn(),
  getSelection: vi.fn(),
  getSavedView: vi.fn(),
  getReaderSettings: vi.fn(),
  saveReaderSettings: vi.fn(),
}))
const scopePresets = vi.hoisted(() => vi.fn())
const getJobs = vi.hoisted(() => vi.fn())
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("@/features/phones/people.api", async (orig) => {
  const real = await orig<{ peopleAPI: object }>()
  return { ...real, peopleAPI: { ...real.peopleAPI, scopePresets } }
})
vi.mock("@/features/phones/job-list", async (orig) => ({ ...(await orig<object>()), getJobs }))
vi.mock("@/features/cases/hooks/use-cases", () => ({ useCase: () => ({ data: { title: "Synthetic case" } }) }))
vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: (q: string) => q.includes("min-width") }))
vi.mock("@/features/phones/hooks/use-collect", () => ({
  useCollectTargets: () => ({ data: [] }),
  useUsedIn: () => ({ usedIn: {}, refresh: vi.fn() }),
}))
vi.mock("./use-thread-matches", () => ({ useThreadMatches: () => ({ isLoading: false, data: undefined }) }))
vi.mock("@/features/phones/hooks/use-stream", () => ({
  useStream: () => ({ status: "idle", error: null, index: null, segments: [], count: 0, total: 0, notice: null, item: () => ({ type: "header", segment: 0 }), ensure: vi.fn(), retry: vi.fn(), reload: vi.fn(), positionOf: () => null, allRows: async () => [], checkSnapshot: async () => true, setFocused: vi.fn() }),
}))
vi.mock("@/features/phones/components/StreamList", () => ({ StreamList: () => <div data-testid="stream" /> }))
vi.mock("@/lib/ux-events", () => ({ trackUx: vi.fn() }))
vi.mock("@/stores/app.store", () => ({ useAppStore: () => ({ sidebarExpanded: true, toggleSidebar: vi.fn() }) }))
const marksFn = vi.hoisted(() => vi.fn())
vi.mock("@/features/phones/marks", () => ({
  HELP_PARAM: "help",
  marksQuery: { queryKey: ["phone-my-marks"], queryFn: marksFn, staleTime: 300_000 },
  newMarksUntil: () => Date.now() + 86_400_000, // the New window is open, so only the paint gate holds the read
  hideNewMarks: async () => ({ marks: { phones_new_hidden: "t" } }),
}))
vi.mock("@/features/auth/hooks/use-auth", () => ({ useAuthStore: () => ({ user: { global_role: "user" } }) }))
vi.mock("@/features/significant/components/CaseLayerSwitcher", () => ({ CaseLayerSwitcher: () => <div>Layers</div> }))
vi.mock("@/lib/route-preload", () => ({ preloadRouteIntent: vi.fn(() => true) }))

import ConversationsPage from "./ConversationsPage"
import CaseStrip from "@/features/phones/ui/CaseStrip"
import { AppSidebar } from "@/components/ui/sidebar"

// requestAnimationFrame withheld: callbacks queue here until paint() runs them, so "before the first paint" is a
// state the test controls instead of a race
const frames: FrameRequestCallback[] = []
function paint() {
  act(() => {
    while (frames.length) frames.shift()!(performance.now())
  })
}

function mount(ui: React.ReactElement, entry = "/cases/case-1/conversations") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/cases/:id/conversations" element={ui} />
            <Route path="/cases/:id/*" element={ui} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe("Conversations start-up defers what the shell does not need", () => {
  beforeEach(() => {
    resetAfterFirstPaintForTest()
    resetKeymapForTest()
    sessionStorage.clear()
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb))
    vi.stubGlobal("cancelAnimationFrame", vi.fn())
    api.getPhones.mockResolvedValue({ case_id: "case-1", phones: [{ extraction_id: "e1", label: "C1", ingested_at: new Date().toISOString() }] })
    api.getSettings.mockResolvedValue({ case_id: "case-1", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null })
    const t = {
      thread_key: "t1", phone: { extraction_id: "e1", label: "C1" }, app: "SyntheticApp", chat_type: null,
      thread_kind: "chat", title: "Synthetic A", participants: [], participant_count: 2, first_instant: null,
      last_instant: null, last_full: "", event_count: 3, event_count_total: 3, deleted_count: 0,
      has_unreadable: false, review: null,
    }
    api.getThreads.mockResolvedValue({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: { threads: 1, threads_total: 1, reviewed: 0, not_reviewed: 1 }, items: [t], sort: "recent" })
    api.getReaderSettings.mockResolvedValue({ stream_density: "compact" })
    scopePresets.mockResolvedValue({ people: [] })
    getJobs.mockResolvedValue({ active: 0, items: [] })
  })
  afterEach(() => {
    frames.length = 0
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("reader settings and scope presets wait for the first paint and still arrive after it", async () => {
    mount(<ConversationsPage />)
    expect(await screen.findByRole("listbox", { name: /^Threads/ })).toBeInTheDocument()
    expect(api.getReaderSettings).not.toHaveBeenCalled()
    expect(scopePresets).not.toHaveBeenCalled()
    paint()
    paint() // the gate waits two frames: one scheduled before the paint, one after it
    await waitFor(() => expect(api.getReaderSettings).toHaveBeenCalled())
    await waitFor(() => expect(scopePresets).toHaveBeenCalledWith("case-1"))
  })

  it("the jobs read waits for the first paint and still arrives after it", async () => {
    mount(<CaseStrip caseId="case-1" problemScreen={null} />, "/cases/case-1/workspace")
    expect(await screen.findByRole("region", { name: "Phone help and jobs" })).toBeInTheDocument()
    expect(getJobs).not.toHaveBeenCalled()
    paint()
    paint()
    await waitFor(() => expect(getJobs).toHaveBeenCalledWith("case-1"))
  })

  it("my-marks waits for the first paint and the New mark still appears from the late answer", async () => {
    marksFn.mockResolvedValue({ marks: {} })
    mount(<AppSidebar />, "/cases/case-1/workspace")
    await waitFor(() => expect(api.getPhones).toHaveBeenCalled())
    await screen.findByText("Phones") // the sidebar has drawn with the phones list in hand, marks still unasked
    expect(marksFn).not.toHaveBeenCalled()
    paint()
    paint()
    await waitFor(() => expect(marksFn).toHaveBeenCalled())
    expect((await screen.findAllByText("New")).length).toBeGreaterThan(0)
  })
})
