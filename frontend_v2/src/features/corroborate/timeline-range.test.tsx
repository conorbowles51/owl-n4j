import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { setSwitch } from "@/lib/ui-switches"
import { corroborateAPI, type Preview } from "./api"
import { getSelection } from "./selection-store"
import { rangeScope } from "./range-scope"
import { TimelineCorroborate } from "./TimelineCorroborate"
import { CorroboratePanel } from "@/features/leads/CorroboratePanel"
import { leadsAPI } from "@/features/leads/api"

const preview: Preview = {
  members: 2, selected: 2,
  scope: { active: true, words: ["from 2026-05-18 to 2026-05-19"], outside: {}, outside_total: 0, no_time: 0, anchors: null, anchors_date_only: 0, kept: null },
  left_out: { count: 0, examples: [] },
  taken: { people: [], times: { from: "2026-05-18", to: "2026-05-19", dated: 2, days: 2, undated: 0 }, places: [], items: [{ type: "timeline_event", count: 2, words: "2 timeline events" }] },
  questions: [],
}

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); setSwitch("corroborate-v2", true) })

describe("Timeline range as a selection", () => {
  it("keeps whole days of the dragged window", () => {
    expect(rangeScope({ from: "2026-05-18T09:30:00Z", to: "2026-05-19T01:00:00Z" })).toEqual({ from: "2026-05-18", to: "2026-05-19" })
    expect(rangeScope({ from: null, to: null })).toEqual({})
  })
  it("holds the events in the range and opens the question already limited to the window", async () => {
    const spy = vi.spyOn(corroborateAPI, "preview").mockResolvedValue(preview)
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter>
      <TimelineCorroborate caseId="c1" range={{ from: "2026-05-18T09:30:00Z", to: "2026-05-19T01:00:00Z" }}
        members={[{ type: "timeline_event", id: "timeline-entry:a" }, { type: "timeline_event", id: "timeline-entry:b" }]} />
      {/* the button opens the Corroborate panel over the page (lx-leads C), mounted app-wide by TraySwitch */}
      <CorroboratePanel />
    </MemoryRouter></QueryClientProvider>)
    vi.spyOn(leadsAPI, "here").mockResolvedValue({ leads: [], total: 0, finder: { status: "done" } })
    fireEvent.click(screen.getByRole("button", { name: /Corroborate 2/ }))
    fireEvent.click(await screen.findByRole("tab", { name: /Ask a new question/ }))
    fireEvent.click(screen.getByRole("button", { name: /Choose the question yourself/ }))
    await screen.findByText(/What Loupe takes from your 2 items/)
    expect(getSelection("c1")[0].screen).toBe("the timeline")
    expect(getSelection("c1")[0].members).toHaveLength(2)
    expect(spy.mock.calls[0][2]).toEqual({ from: "2026-05-18", to: "2026-05-19" })
  })
})
