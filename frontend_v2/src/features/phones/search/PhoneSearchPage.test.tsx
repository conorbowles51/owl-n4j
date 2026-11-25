import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

/** Search every phone (Phones screen 2): counts by kind and phone, highlights, the hit in context, saved
 * differently, next steps. Invented data only. */
const api = vi.hoisted(() => ({ search: vi.fn(), kind: vi.fn(), elsewhere: vi.fn(), context: vi.fn(), save: vi.fn() }))
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  searchPhones: api.search, searchPhonesKind: api.kind, searchPhonesElsewhere: api.elsewhere, hitContext: api.context,
}))
vi.mock("@/features/search/api", async (orig) => ({ ...(await orig<typeof import("@/features/search/api")>()), saveKeywordList: api.save }))
vi.mock("@/features/cases/hooks/use-cases", () => ({ useCase: () => ({ data: { id: "c1" } }) }))
vi.mock("@/features/cases/hooks/use-case-permissions", () => ({ useCasePermissions: () => ({ canEdit: true }) }))
vi.mock("@/features/phones/hooks/use-collect", () => ({ useCollectTargets: () => ({ data: [] }) }))
vi.mock("@/features/phones/ui/use-case-phones", () => ({
  useCasePhones: () => [{ id: "p1", label: "Phone 1", index: 0 }, { id: "p2", label: "Phone 2", index: 1 }, { id: "p3", label: "Phone 3", index: 2 }],
}))
vi.mock("@/features/phones/ui/use-phone-scope", async () => {
  const { EMPTY_SCOPE } = await import("@/features/phones/ui/scope")
  return { useUrlScope: () => ({ scope: EMPTY_SCOPE, apply: vi.fn(), presets: [], recent: [], restored: false, notApplied: [] }) }
})
import PhoneSearchPage from "./PhoneSearchPage"
import { dayPath, hasRoute, stepPath, withElsewhere } from "./step-path"

const phones = [{ extraction_id: "p1", label: "Phone 1" }, { extraction_id: "p2", label: "Phone 2" }, { extraction_id: "p3", label: "Phone 3" }]
const msgHit = {
  kind: "message", title: "Phone 2 WhatsApp message", phone_label: "Phone 2", extraction_id: "p2", time: "12 Mar 2024, 10:14 AM",
  snippet: { before: "Tell ", match: "Pell", after: " the checks are in the drawer" }, record_uid: "r1", evidence_file_id: null,
  event_uid: "e1", thread_key: "t1", thread_title: "Front desk", deleted: true,
  open: { screen: "conversations", params: { phone: "p2", thread: "t1", event: "e1", q: "pell" } },
}
const wordHit = {
  kind: "record", title: "Phone 1 DictionaryWord", phone_label: "Phone 1", extraction_id: "p1", masked: true, field_path: "Word", value_index: 0,
  where: "Keyboard learned word", snippet: { before: "Word: ", match: "••••", after: " (hidden; it holds exactly what you typed)" },
  record_uid: "r2", evidence_file_id: null, open: { screen: "record", params: { record_uid: "r2" } },
}
const result = {
  query: "pell", exact: false, short: null, number_digits: null, phones, total: 31,
  kinds: [
    { kind: "messages", label: "Messages", total: 29, by_phone: { p1: 9, p2: 6, p3: 14 }, deleted: 1 },
    { kind: "contacts", label: "Contacts", total: 0, by_phone: { p1: 0, p2: 0, p3: 0 }, deleted: 0 },
    { kind: "typed_words", label: "Typed words", total: 2, by_phone: { p1: 2, p2: 0, p3: 0 }, deleted: 0 },
  ],
  groups: [
    { kind: "messages", label: "Messages", total: 29, items: [msgHit], next_cursor: "1" },
    { kind: "typed_words", label: "Typed words", total: 2, items: [wordHit], next_cursor: "1" },
  ],
  saved_differently: [{
    identity_keys: ["phone:+17175550221"], person_id: null, name: "Dorian Pell",
    sentence: "Phone 1: “Dorian (office)”. Phone 2: “D Pell”. Phone 3 is this person's own phone.",
    names: [{ extraction_id: "p1", phone: "Phone 1", names: ["Dorian (office)"] }, { extraction_id: "p2", phone: "Phone 2", names: ["D Pell"] }],
    own_phones: [{ extraction_id: "p3", phone: "Phone 3" }],
  }],
  complete: true, limits: [], not_searched: [],
  next_steps: [
    { id: "person", rank: 1, title: "Open Dorian Pell across every phone", why: "Saved under different names on 2 phones.", open: { screen: "person", params: { people: "phone:+17175550221", person_id: null } } },
    { id: "deleted", rank: 2, title: "Read the 1 deleted item first", why: "1 of the 31 results was deleted.", open: { screen: "conversations", params: { q: "pell", deleted: "1" } } },
    { id: "ask", rank: 3, title: "Ask a question about these results", why: "31 results on 3 phones.", open: { screen: "ask", params: { q: "pell" } } },
    { id: "keyword_list", rank: 4, title: "Keep watching for “pell”", why: "Saved as a keyword list.", open: { screen: "keyword_list", params: { q: "pell" } } },
  ],
}
const corroborate = { id: "corroborate", title: "Check it against the rest of the case", why: "The same words are in 21 documents outside the phones.", open: { screen: "corroborate", params: { q: "pell" } } }

function open(url = "/cases/c1/phones/search?q=pell") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[url]}>
        <Routes><Route path="/cases/:id/phones/search" element={<PhoneSearchPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.search.mockResolvedValue(result)
  api.elsewhere.mockResolvedValue({ counts: { documents: 21, payments: 0 }, step: corroborate })
  api.context.mockResolvedValue({ event_uid: "e1", extraction_id: "p2", phone: "Phone 2", thread_key: "t1", thread_title: "Front desk", thread_count: 14, deleted: true, items: [], note: null })
  api.kind.mockResolvedValue({ kind: "messages", label: "Messages", total: 6, items: [msgHit], next_cursor: null, complete: true })
  api.save.mockResolvedValue({})
})

describe("Search every phone", () => {
  it("counts each kind on each phone exactly, and each number opens its results", async () => {
    open()
    const table = await screen.findByRole("table")
    const rows = within(table).getAllByRole("row")
    expect(rows.map((r) => r.textContent)).toEqual(["Found inPhone 1Phone 2Phone 3All", "Messages(1 deleted)961429", "Typed words2··2"])
    fireEvent.click(within(table).getByRole("button", { name: "6 messages on Phone 2" }))
    await waitFor(() => expect(api.kind).toHaveBeenCalled())
    expect(api.kind.mock.calls[0][1]).toMatchObject({ q: "pell", phones: ["p2"] })
    expect(api.kind.mock.calls[0][2]).toBe("messages")
    expect(await screen.findByRole("heading", { name: "Messages on Phone 2 · 6" })).toBeInTheDocument()
  })

  it("marks the matched text, the deleted item and the hidden value, and opens the first hit in context", async () => {
    open()
    const marks = await screen.findAllByText("Pell", { selector: "mark" })
    expect(marks.length).toBeGreaterThan(0)
    expect(screen.getAllByText("Deleted").length).toBeGreaterThan(0)
    expect(screen.getByText("Hidden value")).toBeInTheDocument()
    expect(screen.queryByText(/hunter|Pellucid/)).toBeNull()
    await waitFor(() => expect(api.context).toHaveBeenCalledWith("c1", "e1", expect.anything()))
    const pane = screen.getByRole("region", { name: "In context" })
    expect(await within(pane).findByText(/14 items in this conversation · this one is deleted/)).toBeInTheDocument()
    expect(within(pane).getByRole("link", { name: "Open the thread" })).toHaveAttribute("href", expect.stringContaining("/cases/c1/phones/p2/records/conversations?thread=t1&at=e1&hl=pell"))
  })

  it("notes the person saved under different names, from the contact records", async () => {
    open()
    const note = await screen.findByRole("region", { name: "Saved differently" })
    expect(note).toHaveTextContent("Dorian Pell is saved differently on each phone")
    expect(note).toHaveTextContent("Phone 1: “Dorian (office)”. Phone 2: “D Pell”. Phone 3 is this person's own phone.")
  })

  it("ranks the next steps, the corroborate step taking its place when it arrives", async () => {
    open()
    const steps = await screen.findByRole("region", { name: "Next steps" })
    await waitFor(() => expect(within(steps).getByText("Check it against the rest of the case")).toBeInTheDocument())
    const titles = within(steps).getAllByRole("listitem").map((li) => li.querySelector("p")?.textContent)
    expect(titles).toEqual(["Open Dorian Pell across every phone", "Read the 1 deleted item first", "Check it against the rest of the case", "Ask a question about these results", "Keep watching for “pell”"])
    fireEvent.click(within(steps).getByRole("button", { name: "Save as a keyword list" }))
    await waitFor(() => expect(api.save).toHaveBeenCalledWith("c1", "pell", ["pell"], false))
  })

  it("says what an empty result means and what to do", async () => {
    api.search.mockResolvedValue({ ...result, total: 0, kinds: [], groups: [], saved_differently: [], next_steps: [] })
    open()
    expect(await screen.findByText(/Nothing on these 3 phones matches “pell”\. Check the spelling/)).toBeInTheDocument()
  })
})

describe("next step links carry the people, phones and period", () => {
  const scope = { phones: ["p1", "p2"], from: "2024-03-01", to: "2024-03-31" }
  it("opens the timeline on the phones and dates the step names", () => {
    const s = { id: "empty_phones", title: "", why: "", open: { screen: "timeline", params: { phones: "p3", from: "2024-03-11", to: "2024-06-01" } } }
    expect(stepPath("c1", s, scope)).toBe("/cases/c1/timeline?phones=p3&from=2024-03-11&to=2024-06-01")
  })
  it("opens the deleted items with the search's words and scope", () => {
    expect(stepPath("c1", result.next_steps[1], scope)).toBe("/cases/c1/conversations?q=pell&deleted=1&phones=p1%2Cp2&from=2024-03-01&to=2024-03-31")
  })
  it("ranks a late step after the person and deleted steps", () => {
    expect(withElsewhere(result.next_steps, corroborate).map((s) => [s.id, s.rank])).toEqual([["person", 1], ["deleted", 2], ["corroborate", 3], ["ask", 4], ["keyword_list", 5]])
  })
  it("links a sibling screen only once its route is in the build", () => {
    expect(hasRoute("phones/search")).toBe(true)
    expect(hasRoute("phones/no-such-screen")).toBe(false)
    const person = stepPath("c1", result.next_steps[0], scope)
    expect(person).toBe(hasRoute("phones/person") ? "/cases/c1/phones/person?people=phone%3A%2B17175550221" : "/cases/c1/conversations?tab=people&people=phone%3A%2B17175550221")
    expect(dayPath("c1", "2024-03-12")).toBe(hasRoute("phones/moment")
      ? "/cases/c1/phones/moment?from=2024-03-12T00%3A00%3A00&to=2024-03-12T23%3A59%3A59"
      : "/cases/c1/conversations?from=2024-03-12&to=2024-03-12")
  })
})
