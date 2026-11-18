import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { overlapsAPI, type KindResult, type Overlaps, type Pair } from "./api"
import { OverlapsView } from "./OverlapsView"
import { squareWords } from "./square"
import { OverlapGraph } from "../graph/OverlapGraph"
import { lineWidth } from "../graph/layout"

const none = (words: string): KindResult => ({ count: 0, words })
const person = (key: string, label: string, dossier: string | null, phones = 1) =>
  ({ key, label, full_label: label, dossier_id: dossier, phones, records: 10, position_days: 5, identifiers: [] })

function pair(a: string, b: string, label: string, over: Partial<Pair> = {}, kinds: Partial<Pair["kinds"]> = {}): Pair {
  return {
    a, b, label, direct: false, records: 0, state: "nothing", kinds_found: [],
    kinds: {
      contact: none("No direct contact."), through_others: { ...none("No number or person in contact with both."), go_betweens: [] },
      groups: none("No group chat."), shared: { count: 0, words: "Not searched yet.", searched: false }, place: none("Never together."),
      access: none("No row."), money: none("No payment between them."), documents: none("No document names both."), ...kinds,
    },
    ...over,
  }
}

const DATA: Overlaps = {
  schema: "loupe.overlaps/1", zone: "America/New_York",
  people: [person("ann", "Ann Arden", "d1"), person("bob", "Bob Brook", "d2"), person("phone:p", "the user of Phone P", null)],
  left_out: ["Dan Dale"],
  pairs: [
    pair("ann", "bob", "Ann Arden and Bob Brook", { state: "weighed", direct: true, records: 191, kinds_found: ["contact", "money"],
      level: { key: "strong", name: "Strong link", sentence: "In 5 of 5 nights." },
      leads: [{ id: "l1", title: "Ann and Bob on the theft nights", level: { key: "strong", name: "Strong link" }, lowers: ["Bob works nights there."] }] },
    { contact: { count: 191, words: "191 records on their phones: 169 messages, 22 calls.", records: [
      { ref: "r1", kind: "message", at: "2024-04-20T22:30:00Z", day_only: false, from: "Ann Arden", body: "they let me go today", copies: 2, deleted: false, amount_minor: null, app: null }] },
    money: { count: 5, words: "5 payments between them, $6,000.00 in all.", records: [] } }),
    pair("ann", "phone:p", "Ann Arden and the user of Phone P", { state: "not_weighed", records: 0, kinds_found: ["place"] },
      { place: { count: 17, words: "Their phones together on 17 days.", days: [] } }),
    pair("bob", "phone:p", "Bob Brook and the user of Phone P"),
  ],
  kinds: (["contact", "through_others", "groups", "shared", "place", "access", "money", "documents"] as const).map((k) => ({ key: k, name: k, searched: `everything for ${k}` })),
  worth_a_look: [{ a: "ann", b: "phone:p", label: "x", reasons: ["beside"], words: ["Ann Arden and the user of Phone P never contact each other, yet their phones are together on 17 days."] }],
  documents: { read: 43, naming_two_phone_owners: 16 },
  go_betweens: {
    "phone:p": { key: "phone:p", label: "the user of Phone P", reaches: ["Bob Brook"], records: 67, position_days: 17,
      people: [{ key: "ann", label: "Ann Arden", contacts: 0, place_days: 17, position_days: 40 }, { key: "bob", label: "Bob Brook", contacts: 67, place_days: 5, position_days: 9 }],
      pattern: { times: 5, of: 40, zone: "America/New_York", days: ["2024-03-15"], steps: [
        { at: "x", local: "Fri 22:05", with: "Bob Brook", body: "bay 4 is clear", ref: "s1", reply: { local: "22:07", body: "ok", ref: "s2" } }] } },
  },
  graph: {
    nodes: [person("ann", "Ann Arden", "d1"), person("bob", "Bob Brook", "d2"), person("phone:p", "the user of Phone P", null)],
    lines: [{ a: "ann", b: "bob", records: 191 }],
    dashed: [{ a: "ann", b: "phone:p", via: "bob", via_label: "Bob Brook", money: 0 }],
    squares: [{ people: ["ann", "bob"], documents: [{ file_id: "f1", file: "lease.pdf", people: [{ key: "ann", by: "model", pages: [2] }, { key: "bob", by: "name in the text", pages: [] }] }] }],
    documents: { read: 43, naming_two_phone_owners: 16 },
  },
  notes: ["78 copies are counted once."], seconds: 1,
}

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>)

beforeEach(() => vi.restoreAllMocks())

describe("Who overlaps with whom", () => {
  it("shows a level only from a lead, and says plainly when a pair is not weighed or has nothing", () => {
    expect(squareWords(DATA.pairs[0]).title).toBe("Strong")
    expect(squareWords(DATA.pairs[1])).toMatchObject({ title: "Not weighed yet", sub: "no direct contact" })
    expect(squareWords(DATA.pairs[2]).title).toBe("Nothing in the records")
    expect(squareWords({ ...DATA.pairs[2], state: "no_link", level: { key: "no_link_found", name: "No link found" } }).title).toBe("No link found")
  })

  it("opens a pair with one row per kind, what lowers it, what was not found, and Corroborate this pair", async () => {
    vi.spyOn(overlapsAPI, "get").mockResolvedValue(DATA)
    const sent = vi.fn()
    window.addEventListener("loupe-corroborate-open", sent as EventListener)
    wrap(<OverlapsView caseId="c1" />)
    fireEvent.click(await screen.findByRole("button", { name: /Ann Arden and Bob Brook: Strong/ }))
    const detail = screen.getByTestId("pair-detail")
    expect(within(detail).getByText(/169 messages, 22 calls/)).toBeTruthy()
    expect(within(detail).getByText(/on both phones/)).toBeTruthy()
    expect(within(detail).getByText("Lowers it")).toBeTruthy()
    expect(within(detail).getByText(/searched everything for groups/)).toBeTruthy()
    expect(within(detail).getByText(/not searched in this release/)).toBeTruthy()
    expect(screen.getByText(/Dan Dale/)).toBeTruthy() // never dropped silently
    expect(screen.getByText(/together on 17 days/)).toBeTruthy() // Worth a look
    fireEvent.click(within(detail).getByRole("button", { name: "Corroborate this pair" }))
    const ev = sent.mock.calls[0][0] as CustomEvent
    expect(ev.detail).toMatchObject({ caseId: "c1", members: [{ type: "person", id: "d1" }, { type: "person", id: "d2" }], people: ["ann", "bob"] })
    window.removeEventListener("loupe-corroborate-open", sent as EventListener)
  })
})

describe("A group lead and a pair with nothing between them", () => {
  it("lists the group lead but never shows its level as the pair's", async () => {
    const grouped = { ...DATA, pairs: DATA.pairs.map((p, i) => i !== 2 ? p :
      { ...p, leads: [{ id: "g", title: "Ann, Bob and the user of Phone P: phones in the same place", level: { key: "strong", name: "Strong link" } }] }) }
    vi.spyOn(overlapsAPI, "get").mockResolvedValue(grouped)
    wrap(<OverlapsView caseId="c1" />)
    fireEvent.click(await screen.findByRole("button", { name: /Bob Brook and the user of Phone P: Nothing in the records/ }))
    const detail = screen.getByTestId("pair-detail")
    expect(within(detail).getByText(/Named with others in the lead/)).toBeTruthy()
    expect(within(detail).queryByText(/Level from the lead/)).toBeNull()
  })
})

describe("People, go-betweens and documents", () => {
  it("draws width by records, dashes routes, and opens the unnamed phone's go-between panel with its order", async () => {
    expect(lineWidth(191, 191)).toBe(12)
    expect(lineWidth(1, 191)).toBeLessThan(2)
    vi.spyOn(overlapsAPI, "get").mockResolvedValue(DATA)
    wrap(<OverlapGraph caseId="c1" />)
    const panel = await screen.findByTestId("go-between-panel")
    expect(within(panel).getByText(/people it reaches: Bob Brook/)).toBeTruthy()
    expect(within(panel).getByText(/No contact at all with Ann Arden/)).toBeTruthy()
    expect(within(panel).getByText(/same order on 5 of its 40/)).toBeTruthy()
    expect(within(panel).getByText(/bay 4 is clear/)).toBeTruthy()
    expect(screen.getByText(/16 of 43 name two or more phone owners/)).toBeTruthy()
    expect(screen.getByText(/read by a model, page 2/)).toBeTruthy()
    expect(screen.getByText(/full name in the text/)).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Bob Brook: show who it reaches" }))
    expect(screen.queryByTestId("go-between-panel")).toBeNull() // Bob has no panel in this data
  })
})

describe("A case too large to read at once", () => {
  it("says so with its size on both screens, never an empty grid", async () => {
    const words = "This case holds 434,708 phone records and positions. Who overlaps with whom reads a whole case at once, and only up to 10,000, so it is not shown here."
    vi.spyOn(overlapsAPI, "get").mockResolvedValue({ schema: "loupe.overlaps/1", refused: true, records: 434708, limit: 10000, words })
    const one = wrap(<OverlapsView caseId="c1" />)
    expect(await screen.findByText(words)).toBeTruthy()
    one.unmount()
    wrap(<OverlapGraph caseId="c1" />)
    expect(await screen.findByText(words)).toBeTruthy()
  })
})
