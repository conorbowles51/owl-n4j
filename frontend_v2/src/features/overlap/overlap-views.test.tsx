import { afterEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import type { ReactNode } from "react"
import { setSwitch } from "@/lib/ui-switches"
import { overlapAPI, type AreaCompare as AreaResult, type AroundEvent, type ThreadMarks } from "./api"
import { RowMarks, SavedNames } from "./conversations/marks"
import { AreaCompare } from "./area/AreaCompare"
import AroundEventPage from "./money/AroundEventPage"
import { AlsoElsewherePanel } from "./conversations/AlsoElsewherePanel"

afterEach(() => { setSwitch("corroborate-v2", false); vi.restoreAllMocks() })

function wrap(node: ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const marks: ThreadMarks = {
  zone: "America/New_York",
  marks: {
    r1: { shared: { stock: false, why: null, copies: 10, messages: 5, dates: 5, phones: 2, other_phones: ["Phone 3"] } },
    r2: { shared: { stock: true, why: "On all 6 phones.", copies: 26, messages: 26, dates: 20, phones: 6, other_phones: [] } },
  },
  meanwhile: { r1: [{ record_uid: "m1", at: "2024-03-16T02:10:00Z", time: "22:10", phone: "Lena Marsh's phone", body: "be on the gate at 11. same as before", direction: "from the number" }] },
  names: [{ number: "+14435550131", names: [{ phone: "Desmond Okafor's phone", name: "Curtis Fallowby" }, { phone: "Lena Marsh's phone", name: "T 2" }], own_number_of: "Phone 3", note: "A saved name is a label on one phone, so it counts for little." }],
}

describe("Conversations: what also appears elsewhere", () => {
  it("marks shared words counted once, sets a stock phrase aside, and shows the same number meanwhile", () => {
    render(<><RowMarks data={marks} recordUid="r1" /><RowMarks data={marks} recordUid="r2" /><RowMarks data={marks} recordUid="r3" /></>)
    const shown = screen.getAllByTestId("also-elsewhere-mark")
    expect(shown).toHaveLength(2)
    expect(shown[0].textContent).toContain("The same words in 5 messages on 2 phones on 5 dates, also on Phone 3")
    expect(shown[0].textContent).toContain("counted once")
    expect(shown[0].textContent).toContain("22:10 on Lena Marsh's phone, from the number: “be on the gate at 11. same as before”")
    expect(shown[1].textContent).toContain("A stock phrase, counted for nothing: On all 6 phones.")
  })
  it("names the number on each phone and says a saved name counts for little", () => {
    render(<SavedNames data={marks} />)
    const t = screen.getByTestId("also-elsewhere-names").textContent ?? ""
    expect(t).toContain("saved as “Curtis Fallowby” on Desmond Okafor's phone; saved as “T 2” on Lena Marsh's phone")
    expect(t).toContain("own number of Phone 3")
    expect(t).toContain("counts for little")
  })
})

const area: AreaResult = {
  zone: "America/New_York",
  window: { weekday: 4, start: "22:00", end: "12:00", words: "Fridays 22:00 to Saturday 12:00" },
  period: { from: "2024-01-01", to: "2024-06-30" },
  asked: { nights: ["2024-03-15", "2024-04-12"], basis: "the nights with a position or access row inside an area", unknown: [] },
  compared_with: { nights: ["2024-03-22"], words: "the other 1 Fridays" },
  areas: [{
    index: 0, label: "Area A",
    inside: { positions: 4, position_phones: 2, access_rows: 2, doors: { "Dock 3": 2 }, photo_places: 1, photo_phones: 1, not_positions: 0 },
    baseline: { positions: 0, access_rows: 0, photo_places: 0, nights_with_any: 0 },
    phones: [{ phone: "p6", who: "Lena Marsh", nights: ["2024-03-15", "2024-04-12"], times: [{ time: "22:50", nights: ["2024-03-15", "2024-04-12"], stay_min: 0 }], first: {} }],
    photo_only: [{ phone: "p5", who: "Brianna Cole", nights: ["2024-03-15"] }],
    access: [{ person: "k", who: "Travis Kell", nights: ["2024-03-15", "2024-04-12"], times: [{ time: "23:06", door: "Dock 3", nights: 2 }] }],
    outside_window: [], documents: [{ id: "d1", name: "badge-log.csv", why: "Suggested by Loupe" }], suggested_documents: [],
  }, {
    index: 1, label: "Area B",
    inside: { positions: 2, position_phones: 1, access_rows: 0, doors: {}, photo_places: 0, photo_phones: 0, not_positions: 0 },
    baseline: { positions: 0, access_rows: 0, photo_places: 0, nights_with_any: 0 },
    phones: [{ phone: "p4", who: "Desmond Okafor", nights: ["2024-03-15", "2024-04-12"], times: [{ time: "02:45", nights: ["2024-03-15", "2024-04-12"], stay_min: 0 }], first: {} }],
    photo_only: [], access: [], outside_window: [], documents: [], suggested_documents: [],
  }],
  order: [{ phone: "p4", who: "Desmond Okafor", sequence: [0, 1], nights: 2, of: 2 }],
  strip: [{ night: "2024-03-15", label: "Fri 15 Mar 2024", asked: true, areas: [] }, { night: "2024-04-12", label: "Fri 12 Apr 2024", asked: true, areas: [] }, { night: "2024-03-22", label: "Fri 22 Mar 2024", asked: false, areas: [] }],
  members: [{ type: "phone_record", id: "x" }],
  documents_available: [{ id: "d1", name: "badge-log.csv" }],
}

describe("Conversations: the list of what also appears elsewhere", () => {
  it("lists phrases and deletions, and compares files and pictures only when asked, with full counts", async () => {
    setSwitch("corroborate-v2", true)
    vi.spyOn(overlapAPI, "sharedWords").mockResolvedValue({
      zone: "UTC", phones_in_case: 6, rule: "The rule.",
      also: [{ text: "bay 4 is clear", words: "bay 4 is clear", copies: 10, messages: 5, phones: ["a", "b"], phone_labels: ["Phone 3", "Desmond Okafor's phone"], dates: ["1", "2", "3", "4", "5"], stock: false, why: null, records: ["r1"] }],
      stock: [{ text: "let me check and come back to you", words: "x", copies: 26, messages: 26, phones: ["1", "2", "3", "4", "5", "6"], phone_labels: [], dates: [], stock: true, why: "On all 6 phones.", records: [] }],
      deletions: [{ text: "left something in the tow truck", at: "2024-06-09T23:42:00Z", deleted_on: ["Travis Kell's phone"], kept_on: ["Desmond Okafor's phone"], records: [] }],
    })
    const files = vi.spyOn(overlapAPI, "sharedFiles").mockResolvedValue({
      phones_in_case: 6, listed: 1, counts: { files_common: 2, files_shared: 0, lookalikes: 3 },
      files_common: [{ md5: "m", name: "IMG_00000.jpg", phones: [] }], files_shared: [],
      lookalikes: [{ a: { name: "IMG_4410.JPG", phone: "Mateo Ruiz's phone", file_uid: "a" }, b: { name: "IMG_2107.JPG", phone: "Brianna Cole's phone", file_uid: "b" }, bits_apart: 4, level: "moderate" }],
      lookalike_note: null,
    })
    wrap(<AlsoElsewherePanel caseId="c1" />)
    const panel = await screen.findByTestId("also-elsewhere-panel")
    await within(panel).findByText(/“bay 4 is clear”: 10 copies, 5 messages counted once, on 2 phones/)
    expect(panel.textContent).toContain("deleted on Travis Kell's phone, still on Desmond Okafor's phone")
    expect(panel.textContent).toContain("“let me check and come back to you”: 26 copies on 6 phones. On all 6 phones.")
    expect(files).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId("also-elsewhere-files"))
    const got = await screen.findByTestId("also-elsewhere-files-result")
    expect(got.textContent).toContain("The first 1 of 2 are listed.")
    expect(got.textContent).toContain("IMG_4410.JPG on Mateo Ruiz's phone and IMG_2107.JPG on Brianna Cole's phone: 4 of 64 bits apart")
    expect(got.textContent).toContain("The first 1 of 3 are listed.")
  })
})

describe("Map: drawn areas compared", () => {
  it("shows who is in each area, a photo place never as being there, the baseline, and hands the nights to Financial", async () => {
    setSwitch("corroborate-v2", true)
    vi.spyOn(overlapAPI, "areaCompare").mockResolvedValue(area)
    wrap(<AreaCompare caseId="c1" areas={[[[0, 0], [1, 0], [1, 1]], [[2, 2], [3, 2], [3, 3]]]} />)
    const table = await screen.findByRole("table")
    const cole = within(table).getByText("Brianna Cole").closest("tr")!
    expect(cole.textContent).toContain("only as places of photos received, not positions")
    const kell = within(table).getByText("Travis Kell").closest("tr")!
    expect(kell.textContent).toContain("phone not there; badge at Dock 3 23:06")
    expect(screen.getByTestId("area-compare-baseline").textContent).toContain("nobody in A in these hours")
    expect(screen.getByTestId("area-compare-order").textContent).toContain("Desmond Okafor: A then B on 2 of 2 nights.")
    expect(screen.getByTestId("area-inside-0").textContent).toContain("Places of photos, 1 phone (photo place, not a position)")
    expect(screen.getByText("Money around these nights").getAttribute("href")).toBe("/cases/c1/financial/around-event?dates=2024-03-15,2024-04-12")
  })
  it("sends the records to Corroborate when asked", async () => {
    setSwitch("corroborate-v2", true)
    vi.spyOn(overlapAPI, "areaCompare").mockResolvedValue(area)
    const heard = vi.fn()
    window.addEventListener("loupe-corroborate-open", heard)
    wrap(<AreaCompare caseId="c1" areas={[[[0, 0], [1, 0], [1, 1]]]} />)
    fireEvent.click(await screen.findByText("Corroborate this"))
    window.removeEventListener("loupe-corroborate-open", heard)
    expect(heard).toHaveBeenCalledTimes(1)
    expect((heard.mock.calls[0][0] as CustomEvent).detail.members).toEqual([{ type: "phone_record", id: "x" }])
  })
})

const cell = (amount: string, source: "bank_and_phone" | "phone_only" | "bank_only", gap?: string) => ({
  amount_minor: 0, amount, day: "2024-05-04", source, words: "", check: null, records: [`phone_record:${amount}${source}`], banks: [],
  gap: gap ? { person: "Travis Kell", month: "2024-05", words: gap, statements: [] } : null,
})
const money: AroundEvent = {
  zone: "America/New_York", span_days: 7,
  events: [{ date: "2024-03-15", label: "" }, { date: "2024-05-03", label: "" }],
  columns: [
    { id: "p1", title: "Travis Kell → Lena Marsh", kind: "transfer", payer: "Travis Kell", payee: "Lena Marsh", usual_day: 1, events: 2, of: 2, total_minor: 100000, checks: null, ordinary: false, other_weeks_found: 0 },
    { id: "p2", title: "Travis Kell → unnamed payee", kind: "transfer", payer: "Travis Kell", payee: null, usual_day: 1, events: 2, of: 2, total_minor: 9000, checks: null, ordinary: true, other_weeks_found: 12 },
  ],
  rows: [
    { date: "2024-03-15", label: "", cells: { p1: [cell("$500.00", "bank_and_phone")], p2: [cell("$45.00", "bank_only")] } },
    { date: "2024-05-03", label: "", cells: { p1: [cell("$500.00", "phone_only", "Ask for page 2.")], p2: [] } },
  ],
  other_weeks: { weeks: 20, from: "2024-01-05", to: "2024-06-14", found: { p1: [], p2: [] } },
  one_off: [], rule: "A pattern is the same payer, payee and kind.",
}

describe("Financial: money around an event", () => {
  it("marks BANK + PHONE and PHONE ONLY, names the missing page, says none for every other week, folds ordinary money", async () => {
    setSwitch("corroborate-v2", true)
    vi.spyOn(overlapAPI, "eventChoices").mockResolvedValue({ choices: [] })
    vi.spyOn(overlapAPI, "aroundEvent").mockResolvedValue(money)
    wrap(<Routes><Route path="/cases/:id/financial/around-event" element={<AroundEventPage />} /></Routes>, "/cases/c1/financial/around-event?dates=2024-03-15,2024-05-03")
    const table = await screen.findByRole("table", { name: "Money around each event" })
    expect(within(table).getByText("BANK + PHONE")).toBeTruthy()
    expect(within(table).getByText("PHONE ONLY")).toBeTruthy()
    expect(screen.getAllByTestId("money-gap")[0].textContent).toBe("Ask for page 2.")
    expect(within(table).getByTestId("money-other-weeks").textContent).toContain("none")
    expect(within(table).queryByText("Travis Kell → unnamed payee")).toBeNull()
    expect(screen.getByText("Ordinary money, as common in other weeks (1 pattern)")).toBeTruthy()
    expect(overlapAPI.aroundEvent).toHaveBeenCalledWith("c1", [{ date: "2024-03-15" }, { date: "2024-05-03" }])
  })
})
