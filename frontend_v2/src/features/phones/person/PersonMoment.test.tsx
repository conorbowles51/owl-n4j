import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** Phones redesign screens 3 and 4 with the server stubbed. Synthetic data only (555 numbers, invented names). */
const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<object>()), fetchAPI: api.fetchAPI }))
vi.mock("../ui/use-case-phones", () => ({ useCasePhones: () => [{ id: "p1", label: "Phone 1", index: 0 }, { id: "p2", label: "Phone 2", index: 1 }, { id: "p3", label: "Phone 3", index: 2 }] }))
vi.mock("@/features/conversations/ExportDialog", () => ({ ExportDialog: (p: { words: string }) => <div role="dialog">Export {p.words}</div> }))

import { PersonAcrossPage } from "./PersonAcrossPage"
import { MomentPage } from "../moment/MomentPage"

const card = (id: string, label: string, owner: string, extra: object) => ({
  extraction_id: id, label, owner, owner_key: `phone:+1202555010${id.slice(1)}`, is_own: false, saved_as: [], messages: 0, calls: 0,
  first: "2024-03-11T09:00:00+00:00", last: "2024-03-20T09:00:00+00:00", conversations_href: "/cases/c1/conversations", ...extra,
})
const row = (uid: string, body: string, at: string) => ({
  event_uid: uid, record_uid: `r-${uid}`, kind: "message", app: "WhatsApp", body, subject: null, line: "Dana Reyes → Lee Ortiz",
  time: { instant: at, row: "", full: "", offset_present: true }, call: null,
})
const PERSON = {
  case_id: "c1", person: { name: "Lee Ortiz", identifiers: ["+1 202-555-0103"], name_basis: "contact_on_a_phone", keys: ["phone:+12025550103"], own_phones: ["p3"] },
  with: null, zone: "UTC",
  phones: [card("p1", "Phone 1", "Dana Reyes", { saved_as: ["Lee (office)"], messages: 1 }), card("p2", "Phone 2", "Sam Hale", { saved_as: ["L Ortiz"], messages: 2 }),
    card("p3", "Phone 3", "Lee Ortiz", { is_own: true, messages: 5 })],
  summary: { messages: 5, calls: 0, apps: ["WhatsApp"], phones_holding: 3, phones_in_scope: 3, first: "2024-03-11T09:00:00+00:00", last: "2024-03-20T09:00:00+00:00", no_time: 0, copies: 8 },
  records: [
    { row: row("e1", "can you cover the desk", "2024-03-11T09:00:00+00:00"), on: ["p1", "p3"], missing: [], deleted_on: [], copies: [], spread_s: 0, diff: [] },
    { row: row("e2", "leave me your login", "2024-03-11T09:01:00+00:00"), on: ["p3"], missing: [{ extraction_id: "p1", not_recording: false }], deleted_on: [], copies: [], spread_s: 0, diff: ["missing"] },
  ],
  records_total: 5, contacts_total: 5, only: null, offset: 0, limit: 200,
  compare: [{ on: ["p1", "p3"], messages: 1, calls: 0 }, { on: ["p3"], messages: 2, calls: 0 }],
  volume: { bucket: "week", rows: [{ start: "2024-03-11", by_phone: { p1: 1, p2: 2, p3: 5 } }] },
  differs: [
    { code: "missing", title: "On one phone, missing from another", n: 2, explained: 1, body: "1 of them falls where that phone was not recording." },
    { code: "deleted", title: "Deleted on one phone, kept on another", n: 1, body: "1 deleted on Phone 3 and still on Phone 2." },
    { code: "names", title: "Saved under different names", n: 2, body: "“Lee (office)” on Phone 1, “L Ortiz” on Phone 2." },
    { code: "clocks", title: "Clocks disagree", n: 0, body: "Where the same contact is on two phones, the times match to the second (3 contacts)." },
  ],
  places: { own_phones: ["p3"], squares: [], observations: 0, words: "Their phone holds no located points." },
  next_steps: [
    { code: "open_unexplained", rank: 1, title: "Look at the 1 contact missing from a phone for no clear reason", why: "1 of the 2 missing contacts fall where the phone was not recording.", action: "Open it", filter: "missing_unexplained" },
    { code: "export", rank: 2, title: "Export their contact as a PDF", why: "5 messages and 0 calls on 3 phones.", action: "Export as PDF" },
  ],
  rule_words: "Messages that appear on more than one phone are shown once.",
}

function Where() {
  const l = useLocation()
  return <span data-testid="where">{l.search}</span>
}

function mount(path: string, route: string, el: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={<>{el}<Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("One person across every phone", () => {
  it("shows a card per phone with how it saved them, each contact once with its phones, and what differs", async () => {
    api.fetchAPI.mockResolvedValue(PERSON)
    mount("/cases/:id/phones/person", "/cases/c1/phones/person?people=phone:%2B12025550103", <PersonAcrossPage />)
    expect(await screen.findByRole("heading", { name: "Lee Ortiz" })).toBeInTheDocument()
    expect(api.fetchAPI.mock.calls[0][0]).toContain("/api/phones/person-across?case_id=c1&people=phone%3A%2B12025550103")
    expect(screen.getByText("Saved as “Lee (office)”")).toBeInTheDocument()
    expect(screen.getByText("Their own phone")).toBeInTheDocument()
    expect(screen.getByText(/on Phone 1 and Phone 3/)).toBeInTheDocument()
    expect(screen.getByText(/on Phone 3, missing from Phone 1/)).toBeInTheDocument()
    expect(screen.getByText("Showing 1 to 2 of 5.")).toBeInTheDocument()
    // a difference card opens its records: the list is asked for again with only=
    fireEvent.click(screen.getByRole("button", { name: /On one phone, missing from another/ }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toContain("only=missing"))
    // next steps come from the result, and the first one opens its list
    fireEvent.click(await screen.findByRole("button", { name: "Open it" }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toContain("only=missing_unexplained"))
    fireEvent.click(screen.getAllByRole("button", { name: "Export as PDF" })[0])
    expect(await screen.findByRole("dialog")).toHaveTextContent("Export Lee Ortiz on 3 phones")
  })

  it("compares every phone at once, not only two", async () => {
    api.fetchAPI.mockResolvedValue(PERSON)
    mount("/cases/:id/phones/person", "/cases/c1/phones/person?people=k&tab=compare", <PersonAcrossPage />)
    expect(await screen.findByText("All 3 phones are compared at once.", { exact: false })).toBeInTheDocument()
    expect(screen.getAllByRole("row")).toHaveLength(3)
  })

  it("says what to do when no person is chosen", () => {
    mount("/cases/:id/phones/person", "/cases/c1/phones/person", <PersonAcrossPage />)
    expect(screen.getByRole("status")).toHaveTextContent("No person is chosen")
  })
})

const MOMENT = {
  case_id: "c1", from: "2024-03-12T09:00:00+00:00", to: "2024-03-12T12:00:00+00:00", zone: "UTC",
  phones: [
    { extraction_id: "p1", label: "Phone 1", owner: "Dana Reyes", not_recording: [{ start: "2024-03-12T09:40:00+00:00", end: "2024-03-12T10:50:00+00:00" }], marks: [{ kind: "message", at: "2024-03-12T09:20:00+00:00", record_uid: "r1" }], counts: { messages: 1, calls: 0, places: 0, use: 0 } },
    { extraction_id: "p2", label: "Phone 2", owner: "Sam Hale", not_recording: [], marks: [], counts: { messages: 0, calls: 0, places: 0, use: 0 } },
  ],
  pairs: [{ phones: ["p1", "p2"], strip: Array.from({ length: 12 }, (_, i) => ({ start: "2024-03-12T09:00:00+00:00", end: "2024-03-12T09:15:00+00:00", state: i < 4 ? "together" : "unknown" })), episodes: [], compared: 3, words: "Phone 1 and Phone 2: together 09:00 to 10:00 (UTC)." }],
  records: [
    { kind: "message", at: "2024-03-12T09:20:00+00:00", on: ["p1"], app: "WhatsApp", who: "Dana Reyes → Sam Hale", text: "on my way", deleted_on: [], record_uids: ["r1"] },
    { kind: "not_recording", at: "2024-03-12T09:40:00+00:00", end: "2024-03-12T10:50:00+00:00", on: ["p1"], app: null, who: null, text: "No records until 10:50: the phone was not recording", deleted_on: [], record_uids: [] },
  ],
  places: [], summary: "1 record in this window on 1 phone. Phone 1 has none from 09:40 to 10:50 because it was not recording.",
  strip_words: { together: "Together (within 150 m)", maybe: "Possibly together", apart: "Apart", unknown: "Not known" }, together_rule: "Two phones are together when…",
  next_steps: [{ code: "wider", rank: 1, title: "Widen to the whole of 12 March 2024", why: "See what led up to this window.", action: "Show the whole day", from: "2024-03-12T00:00:00+00:00", to: "2024-03-13T00:00:00+00:00" }],
}

describe("Around a moment", () => {
  it("draws a lane per phone with not recording apart from quiet, a strip per pair, and moves the window", async () => {
    api.fetchAPI.mockResolvedValue(MOMENT)
    mount("/cases/:id/phones/moment", "/cases/c1/phones/moment?from=2024-03-12T09:00:00Z&to=2024-03-12T12:00:00Z", <MomentPage />)
    expect(await screen.findByText(/1 record in this window on 1 phone/)).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /Phone 1: 1 messages.*not recording 09:40 to 10:50/ })).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "Phone 1 and Phone 2: together 09:00 to 10:00 (UTC)." })).toBeInTheDocument()
    expect(screen.getByText("No records until 10:50: the phone was not recording")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Show the whole day" })).toHaveAttribute("href", expect.stringContaining("from=2024-03-12T00%3A00%3A00%2B00%3A00"))
    fireEvent.click(screen.getByRole("button", { name: "Later" }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toContain("from=2024-03-12T12%3A00%3A00.000Z"))
  })

  it("saves the window as a key moment through saved views", async () => {
    api.fetchAPI.mockImplementation((url: string) => Promise.resolve(url.startsWith("/api/phones/views") ? { id: "v1", entry_id: "n1", event_count: 1, words: "x" } : MOMENT))
    mount("/cases/:id/phones/moment", "/cases/c1/phones/moment?from=2024-03-12T09:00:00Z&to=2024-03-12T12:00:00Z", <MomentPage />)
    fireEvent.click(await screen.findByRole("button", { name: "Save as a key moment" }))
    await waitFor(() => expect(api.fetchAPI).toHaveBeenCalledWith("/api/phones/views", expect.objectContaining({ method: "POST" })))
    const body = api.fetchAPI.mock.calls.find((c) => c[0] === "/api/phones/views")![1].body
    expect(body.filter).toEqual({ case_id: "c1", phones: ["p1", "p2"], from_instant: MOMENT.from, to_instant: MOMENT.to })
    expect(await screen.findByRole("status")).toHaveTextContent("Saved to the case's Workspace")
  })

  it("says what to do when the window has no clear start and end", () => {
    mount("/cases/:id/phones/moment", "/cases/c1/phones/moment?from=nonsense", <MomentPage />)
    expect(screen.getByRole("alert")).toHaveTextContent("no clear start and end")
  })
})
