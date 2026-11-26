import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** Screen 8 (lx-mentions): counts by kind and outcome, the words marked in their message, the selected mention's
 * checks with Loupe's reading labelled, next steps from the result, and one batched request for marks. Invented data. */
const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))
vi.mock("../phones-query", () => ({ phonesQuery: () => ({ queryKey: ["phones", "c1"], queryFn: async () => ({ phones: [{ extraction_id: "p1", label: "Phone 1" }, { extraction_id: "p2", label: "Phone 2" }] }) }) }))
vi.mock("../ui/use-phone-scope", () => ({ useUrlScope: () => ({ scope: { phones: [] }, apply: () => undefined }) }))

import MentionsPage from "./MentionsPage"
import { MentionMark } from "./MentionMark"

const mention = (id: string, outcome: string, label: string, phrase: string, body: string) => ({
  id, kind: "travel", kind_label: "Travel", phrase, start: body.indexOf(phrase), end: body.indexOf(phrase) + phrase.length, body,
  record_uid: `r-${id}`, record_kind: "message", at: "2025-03-05T19:12:00Z", phone: "p1", phone_label: "Phone 1",
  copies: [{ record_uid: `r-${id}`, phone: "p1", phone_label: "Phone 1" }, { record_uid: `s-${id}`, phone: "p2", phone_label: "Phone 2" }],
  app: "WhatsApp", from: "Ada Quill", to: ["Ben Rook"], who: ["Ada Quill"], with: [], when: { start: "2025-03-07T18:00:00Z", end: "2025-03-08T04:00:00Z" },
  where: { name: "Gull Cabin", located: true }, how: "driving", amounts_minor: [], words: ["Gull Cabin"], reader: "rules", state: "read",
  read_by: "Read by Loupe · not confirmed", corrected_fields: [], original: null, decided_by: null, decided_at: null,
  outcome, outcome_label: label, basis: "2 independent sources agree", why: "Phone 1 is at Gull Cabin.", checked_at: null,
})

const list = {
  counts: [{ kind: "travel", label: "Travel", fits: 1, against: 1, unknown: 0, total: 2 }, { kind: "money", label: "Money", fits: 0, against: 0, unknown: 3, total: 3 }],
  total: 2, shown: 2, offset: 0,
  mentions: [mention("m2", "contradicts", "Contradicts", "in bed all day", "Not coming in, in bed all day"),
    mention("m1", "fits_strongly", "Fits, fairly strongly", "I'll drive up Friday night", "Gull Cabin this weekend? I'll drive up Friday night")],
  phones: [{ phone: "p1", phone_label: "Phone 1", texts: 40, rules: { id: "r", phone: "p1", phone_label: "Phone 1", reader: "rules", status: "done", texts_total: 40, texts_read: 40, mentions_found: 5, model_calls: 0, cost_usd: 0, error: null, started_by: "x", started_at: null, finished_at: null }, model: null, outside_allowed: false },
    { phone: "p2", phone_label: "Phone 2", texts: 10, rules: null, model: null, outside_allowed: false }],
  how: [{ kind: "travel", label: "Travel", how: "the phone's places on the way" }],
  next_steps: [{ n: 1, title: "Look at “in bed all day” first", why: "Phone 1 was elsewhere.", action: "open_mention", label: "Open the contradiction", mention_id: "m2", primary: true }],
  read_by: "Read by Loupe · not confirmed",
}

const detail = {
  ...mention("m2", "contradicts", "Contradicts", "in bed all day", "Not coming in, in bed all day"),
  checks: [{ source: "places", source_label: "Places", verdict: "contradicts", verdict_label: "Contradicts", text: "Phone 1 is elsewhere at all 2 positions.", note: "Positions are within 10 m.", refs: [{ ref: "phone_record:x1", label: "Ada · Wed 5 Mar, 14:05" }], refs_total: 3, strong: true }],
  would_test: [], window: { start: "2025-03-05T08:00:00Z", end: "2025-03-05T22:00:00Z", label: "Wed 05 Mar 2025 08:00 to 22:00" },
}

function route(url: string) {
  if (url.includes("/phone-mentions/marks")) return Promise.resolve({ marks: { u1: [{ id: "m1", kind: "travel", kind_label: "Travel", start: 0, end: 4, phrase: "made it", outcome: "fits_weakly", outcome_label: "Fits weakly", state: "read", read_by: "Read by Loupe · not confirmed" }] } })
  if (/phone-mentions\/m2$/.test(url)) return Promise.resolve(detail)
  if (url.includes("/elsewhere/statement?part=financial")) return Promise.resolve({ parts: [{ source: "financial", label: "Money", state: "done", searched: "", items: [{ relation: "possible_match", relation_label: "Possible match", text: "$40.00 to Gull Fuel", reason: "Same day; nothing names the people.", citation: { kind: "transaction", id: "t9", label: "Payment 7 Mar" } }] }] })
  if (url.includes("/elsewhere/statement")) return Promise.resolve({ parts: [{ source: "x", label: "X", state: "done", searched: "", items: [{ relation: "nothing_found", relation_label: "Nothing found", text: "", reason: "" }] }] })
  if (url.includes("/phone-mentions?")) return Promise.resolve(list)
  return Promise.reject(new Error(`unexpected ${url}`))
}

const wrap = (ui: React.ReactNode, at = "/cases/c1/phones/mentions") => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[at]}><Routes><Route path="/cases/:id/phones/mentions" element={ui} /><Route path="*" element={ui} /></Routes></MemoryRouter>
  </QueryClientProvider>)

describe("Mentions, checked against the case", () => {
  it("lists contradictions first with the words marked, counts by kind, and the selected mention's checks", async () => {
    fetchAPI.mockReset().mockImplementation((url: string) => route(url))
    wrap(<MentionsPage />)
    const items = await screen.findAllByRole("listitem")
    const listEl = screen.getByRole("region", { name: "Mentions in their messages" })
    const rows = within(listEl).getAllByRole("button")
    expect(rows[0]).toHaveTextContent("Contradicts")
    expect(rows[0].querySelector("mark")).toHaveTextContent("in bed all day")
    expect(rows[0]).toHaveTextContent("Phone 2")   // the copy on the other phone is named
    expect(items.length).toBeGreaterThan(0)
    const table = screen.getByRole("table", { name: "Mentions by kind and outcome" })
    expect(within(table).getByRole("button", { name: "1 Travel mentions that the records go against" })).toBeInTheDocument()
    const side = screen.getByRole("complementary", { name: "Checks for the selected mention" })
    expect(await within(side).findByText("Phone 1 is elsewhere at all 2 positions.")).toBeInTheDocument()
    expect(within(side).getByText(/Read by Loupe · not confirmed/)).toBeInTheDocument()
    expect(within(side).getByRole("link", { name: "Ada · Wed 5 Mar, 14:05" })).toHaveAttribute("href", "/cases/c1/records/x1")
    expect(within(side).getByText("and 2 more")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open the contradiction" })).toBeInTheDocument()
    const elsewhere = within(side).getByRole("region", { name: "Elsewhere in the case" })
    expect(await within(elsewhere).findByText(/Money · Possible match:/)).toBeInTheDocument()
    expect(within(elsewhere).getByRole("link", { name: "Payment 7 Mar" })).toHaveAttribute("href", "/cases/c1/financial?view=transactions&payment=t9")
    expect(screen.getAllByText(/Word rules only: this phone.s Outside services are not allowed/)).toHaveLength(2)
    expect(screen.getByRole("button", { name: "Read this phone" })).toBeInTheDocument()
  })

  it("starts a reading of an unread phone with the word rules", async () => {
    fetchAPI.mockReset().mockImplementation((url: string, opts?: { method?: string; body?: unknown }) =>
      opts?.method === "POST" ? Promise.resolve({ id: "r2", status: "running" }) : route(url))
    wrap(<MentionsPage />)
    fireEvent.click(await screen.findByRole("button", { name: "Read this phone" }))
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith("/api/cases/c1/phone-mentions/runs", { method: "POST", body: { phone: "p2", reader: "rules" } }))
    fireEvent.click(screen.getByRole("button", { name: "Read again" }))   // a phone already read is read and checked afresh
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith("/api/cases/c1/phone-mentions/runs", { method: "POST", body: { phone: "p1", reader: "rules" } }))
  })
})

describe("The mention mark on a message", () => {
  it("asks once for the rows of a moment and links to the mention", async () => {
    fetchAPI.mockReset().mockImplementation((url: string) => route(url))
    wrap(<div><MentionMark caseId="c9" recordUid="u1" /><MentionMark caseId="c9" recordUid="u2" /></div>, "/x")
    const link = await screen.findByRole("link", { name: /Travel.*Fits weakly/ })
    expect(link).toHaveAttribute("href", "/cases/c9/phones/mentions?mention=m1")
    expect(fetchAPI.mock.calls.filter(([u]) => String(u).includes("/marks"))).toHaveLength(1)
    expect(String(fetchAPI.mock.calls[0][0])).toContain("records=u1%2Cu2")
  })
})
