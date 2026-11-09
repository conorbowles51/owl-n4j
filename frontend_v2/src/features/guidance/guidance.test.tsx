import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { fetchAPI } from "@/lib/api-client"
import type { EvidenceJob } from "@/types/evidence.types"
import type { GuidanceSettings } from "./api"
import { announce, useNextSteps } from "./announce"
import { nextSteps } from "./next-steps"
import { NextStepsHost } from "./NextStepsHost"
import { startSteps } from "./start-steps"
import { TourHost } from "./TourHost"
import { findTarget, tourArea, TOURS } from "./tours"
import { finishedBetween, processedFacts } from "./watchers"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
const api = vi.mocked(fetchAPI)

const settings = (over: Partial<GuidanceSettings> = {}): GuidanceSettings => ({
  guidance: "on", source: "default", case_default: null, tips_off: [], tours: {}, history_collapsed: false, ...over,
})

/** A fake server for the guidance marks: what is saved stays saved across a "sign-out" (a new query client). */
function server(initial = settings()) {
  let saved = initial
  const calls: { endpoint: string; body?: unknown; method?: string }[] = []
  api.mockImplementation(async (endpoint: string, options: { method?: string; body?: unknown } = {}) => {
    calls.push({ endpoint, body: options.body, method: options.method })
    if (endpoint.startsWith("/api/guidance/me/tours/")) {
      const area = decodeURIComponent(endpoint.split("/").pop()!)
      const body = options.body as { state?: "done" | "skipped"; step?: number }
      saved = { ...saved, tours: { ...saved.tours, [area]: { ...saved.tours[area], ...(body.state ? { state: body.state } : {}), ...(body.step !== undefined ? { step: body.step } : {}) } } }
    } else if (endpoint === "/api/guidance/me" && options.method === "PUT") {
      saved = { ...saved, guidance: (options.body as { guidance: "on" | "off" }).guidance, source: "user" }
    } else if (endpoint.startsWith("/api/guidance/me/tips-off")) {
      saved = { ...saved, tips_off: [...saved.tips_off, (options.body as { kind: string }).kind] }
    }
    return saved as never
  })
  return { calls, get saved() { return saved } }
}

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname + l.search}</p>
}

function wrap(node: ReactNode, path = "/cases/c1/workspace", client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases/:id/*" element={<>{node}<Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  api.mockReset()
  useNextSteps.setState({ cards: [] })
})
afterEach(() => vi.useRealTimers())

describe("next steps after an action", () => {
  it("finishing a document's processing gives the true counts and working links", () => {
    const card = nextSteps("c1", { kind: "document-processed", files: 1, names: 12, links: 30, fileName: "11 ARRENDO.pdf", evidenceId: "f9" })!
    expect(card.title).toBe("11 ARRENDO.pdf processed: 12 names and 30 links between them found.")
    expect(card.steps.map((s) => [s.label, s.to])).toEqual([
      ["Review the names", "/cases/c1/table"],
      ["Open the graph", "/cases/c1/graph"],
      ["See the timeline", "/cases/c1/timeline"],
      ["Ask the agent", "/cases/c1/agent"],
    ])
  })

  it("a step whose target has nothing is not shown, and an action with no step shows nothing", () => {
    const none = nextSteps("c1", { kind: "document-processed", files: 2, names: 0, links: 0 })
    expect(none).toBeNull()
    const noLinks = nextSteps("c1", { kind: "document-processed", files: 2, names: 3, links: 0 })!
    expect(noLinks.steps.map((s) => s.id)).not.toContain("graph")
    const statement = nextSteps("c1", { kind: "statement-imported", payments: 40, needsLook: 0 })!
    expect(statement.steps.map((s) => s.id)).toEqual(["payments", "follow"])
    expect(nextSteps("c1", { kind: "export-done", fileName: "x.zip", href: null })).toBeNull()
  })

  it("the card stays until a step is followed, and the step goes where it says", async () => {
    api.mockResolvedValue(settings() as never)
    wrap(<NextStepsHost caseId="c1" />)
    act(() => void announce("c1", { kind: "document-processed", files: 3, names: 12, links: 4 }))
    expect(await screen.findByText("3 files processed: 12 names and 4 links between them found.")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: /Open the graph/ }))
    expect(screen.getByTestId("where").textContent).toBe("/cases/c1/graph")
    expect(screen.queryByTestId("next-steps-card")).toBeNull()
  })

  it("with guidance off the card does not pop up but waits behind a quiet link", async () => {
    server(settings({ guidance: "off", source: "user" }))
    wrap(<NextStepsHost caseId="c1" />)
    act(() => void announce("c1", { kind: "merge-done", name: "Ann Lee", entityKey: "person:ann", merged: 2 }))
    const link = await screen.findByRole("button", { name: "Next steps (1)" })
    expect(screen.queryByTestId("next-steps-card")).toBeNull()
    fireEvent.click(link)
    expect(screen.getByText("2 entries merged into Ann Lee.")).toBeTruthy()
  })
})

describe("first-visit tours", () => {
  it("every area has 3 to 5 steps and every case screen maps to its area", () => {
    for (const tour of Object.values(TOURS)) expect(tour.steps.length).toBeGreaterThanOrEqual(3)
    for (const tour of Object.values(TOURS)) expect(tour.steps.length).toBeLessThanOrEqual(5)
    expect(tourArea("/cases/c1")).toBe("workspace")
    expect(tourArea("/cases/c1/phone-analyses/plans")).toBe("phones")
    expect(tourArea("/cases/c1/financial?view=overview")).toBe("financial")
    expect(tourArea("/cases/c1/settings")).toBeNull()
  })

  it("points at the first control on screen, by selector or by its words", () => {
    document.body.innerHTML = '<main><button>Upload files</button><button hidden-in-layout>Process</button></main>'
    // jsdom lays nothing out: give the first button a size, as a browser would; the second stays unlaid (hidden)
    const [upload] = Array.from(document.querySelectorAll("button"))
    upload.getBoundingClientRect = () => ({ width: 80, height: 24, top: 0, left: 0, bottom: 24, right: 80, x: 0, y: 0, toJSON: () => ({}) })
    expect(findTarget(["text=Process"])).toBeNull()
    const el = findTarget(['[data-guide="nope"]', "text=Upload"])
    expect(el?.textContent).toBe("Upload files")
    expect(findTarget(['[data-guide="nope"]'])).toBeNull()
    document.body.innerHTML = ""
  })

  it("opens by itself once, can be skipped, and the skip is kept for the next session", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const s = server()
    const first = wrap(<TourHost caseId="c1" />, "/cases/c1/graph")
    await act(async () => void vi.advanceTimersByTime(1500))
    expect(await screen.findByTestId("tour-popup")).toBeTruthy()
    expect(screen.getByText("Who is linked to whom")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Skip tour" }))
    await waitFor(() => expect(s.saved.tours.graph?.state).toBe("skipped"))
    first.unmount()
    // signed out and in again: a new client reads the saved marks; the tour stays closed
    wrap(<TourHost caseId="c1" />, "/cases/c1/graph")
    await act(async () => void vi.advanceTimersByTime(1500))
    expect(screen.queryByTestId("tour-popup")).toBeNull()
  })

  it("resumes at the step where it was left", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const s = server()
    const first = wrap(<TourHost caseId="c1" />, "/cases/c1/financial")
    await act(async () => void vi.advanceTimersByTime(1500))
    fireEvent.click(await screen.findByRole("button", { name: "Next" }))
    await waitFor(() => expect(s.saved.tours.financial?.step).toBe(1))
    first.unmount()
    wrap(<TourHost caseId="c1" />, "/cases/c1/financial")
    await act(async () => void vi.advanceTimersByTime(1500))
    expect(await screen.findByText("Every payment")).toBeTruthy()
    expect(screen.getByText("Financial · 2 of 5")).toBeTruthy()
  })

  it("turning guidance off stops popups for that person across sessions", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const s = server()
    const first = wrap(<TourHost caseId="c1" />, "/cases/c1/map")
    await act(async () => void vi.advanceTimersByTime(1500))
    fireEvent.click(await screen.findByRole("button", { name: "Turn guidance off" }))
    await waitFor(() => expect(s.saved.guidance).toBe("off"))
    expect(screen.queryByTestId("tour-popup")).toBeNull()
    first.unmount()
    for (const path of ["/cases/c1/map", "/cases/c1/timeline", "/cases/c1/agent"]) {
      const next = wrap(<TourHost caseId="c1" />, path)
      await act(async () => void vi.advanceTimersByTime(1500))
      expect(screen.queryByTestId("tour-popup")).toBeNull()
      next.unmount()
    }
    expect(s.calls.filter((c) => c.method === "PUT" && c.endpoint === "/api/guidance/me")).toHaveLength(1)
  })
})

describe("start here and processing watch", () => {
  it("offers only steps that lead somewhere", () => {
    const counts = { files: 4, unprocessed: 4, phones: 0, payments: 0, theories: 0, unavailable: [] }
    expect(startSteps("c1", counts).map((s) => s.id)).toEqual(["process", "theory"])
    expect(startSteps("c1", { ...counts, files: 0, unprocessed: 0 }).map((s) => s.id)).toEqual(["upload"])
    expect(startSteps("c1", { files: 9, unprocessed: 0, phones: 2, payments: 120, theories: 1, unavailable: [] }).map((s) => s.id)).toEqual(["money", "phones", "graph"])
  })

  it("tells the documents that finished since the last read, with their counts", () => {
    const job = (id: string, status: string, entities = 0, links = 0) =>
      ({ id, status, entity_count: entities, relationship_count: links, file_name: `${id}.pdf`, evidence_file_id: `e-${id}` }) as unknown as EvidenceJob
    const { done, failed } = finishedBetween(new Set(["a", "b", "c"]), [job("a", "completed", 5, 2), job("b", "failed"), job("c", "capturing"), job("d", "completed", 9, 9)])
    expect(done.map((j) => j.id)).toEqual(["a"])
    expect(failed.map((j) => j.id)).toEqual(["b"])
    expect(processedFacts(done, failed)).toEqual({ kind: "document-processed", files: 1, names: 5, links: 2, failed: 1, fileName: "a.pdf", evidenceId: "e-a" })
  })
})
