import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { leadsAPI } from "@/features/leads/api"
import { corroborateAPI } from "../api"
import type { Corroboration, DayTile } from "../result-types"
import { AnswerView } from "./AnswerView"
import { changes, innocentExplanations, nextSteps, template } from "./answer-model"

vi.mock("@/features/phones/collect-targets", () => ({ useCollectTargets: () => ({ targets: [], note: null, loading: false, error: null }) }))
vi.mock("@/features/phones/ui/use-case-phones", () => ({ useCasePhones: () => [{ id: "e2", label: "Phone 2", index: 1 }, { id: "e3", label: "Phone 3", index: 2 }] }))

const days = ["2024-03-04", "2024-03-07", "2024-03-14"]
function tile(id: string, outcome: DayTile["outcome"], detail: string, events = ["Check 2201 · $1,940.00"]): DayTile {
  return { instance: id, date: `Mon ${id.slice(8)} Mar 2024`, hours: id, events, event_refs: ["financial_transaction:x"], outcome,
           outcome_words: { present: "Together", absent: "Apart", no_data: "No location data" }[outcome], detail, records: outcome === "present" ? ["phone_record:a"] : [] }
}
const C: Corroboration = {
  schema: "loupe.corroborate/1",
  question: { kind: "together", text: "Were Marisol Teague and Dorian Pell together on 3 instances?", chips: { people: ["person:m", "person:d"] } },
  level: { key: "probable", name: "Probable link", sentence: "Together on 2 of 3 deposit days; on 9 of 50 ordinary days.", reasons: [], rule: "r" },
  comparison: { kind: "same_people_ordinary", words: "w", incident: days.map((d) => ({ id: d, label: d, start: `${d}T00:00:00Z`, end: `${d}T23:59:00Z` })), ordinary: [] },
  grid: [
    { signal: "together:m:d", link_kind: "together", label: "Marisol Teague and Dorian Pell in the same place", cells: {}, incident: { present: 2, of: 3 }, ordinary: { present: 9, of: 50 }, weight: "full", separates: true, records: {}, record_counts: { [days[0]]: 2, [days[1]]: 2 } },
    { signal: "contact:m:d", link_kind: "contact", label: "Marisol Teague and Dorian Pell in contact", cells: {}, incident: { present: 2, of: 3 }, ordinary: { present: 4, of: 50 }, weight: "full", separates: false, records: {}, record_counts: { [days[0]]: 20, [days[2]]: 11 } },
  ],
  checks: [
    { check: "workplace", outcome: "ruled_out", words: "5 of the 6 meetings were after the practice closed." },
    { check: "household", outcome: "checked", words: "Not together on most ordinary days." },
    { check: "busy_place", outcome: "weighed_low", words: "2 of the days rest on cell-tower locations." },
  ],
  people: [{ key: "person:m", label: "Marisol Teague", phones: [{ id: "e2", label: "Phone 2" }] }, { key: "person:d", label: "Dorian Pell", phones: [{ id: "e3", label: "Phone 3" }] }],
  not_in_pattern: [{ who: "Priya Halloran", key: "person:p", found: [{ signal: "contact", instances: 2 }], says: "In the pattern's instances: contact on 2", searched: [] }],
  gaps: [],
  look_further: [],
  days: {
    events_phrase: "the 3 check deposit days", events_source: "from the financial records", people: ["Marisol Teague", "Dorian Pell"], row: "together:m:d",
    relation: { link_kind: "together", word: "together", label: "x", people: ["person:m", "person:d"], definition: "“Together” means Marisol Teague's phone (Phone 2) and Dorian Pell's phone (Phone 3) were placed within each other's accuracy plus 50 m, within 15 minutes of each other, from their location records.", present: "Together", absent: "Apart", no_data: "No location data" },
    tiles: [tile(days[0], "present", "7:10 PM to 8:25 PM"), tile(days[1], "present", "6:40 PM to 7:30 PM"), tile(days[2], "no_data", "Dorian Pell's phone has no locations that day, so it counts neither way.")],
    ordinary: { of: 52, present: 9, absent: 41, no_data: 2, noun: "other days", span: "Tue 2 Jan 2024 to Sat 18 May 2024", words: "Together on 9, apart on 41, no location data on 2",
                cells: Array.from({ length: 52 }, (_, i) => ({ instance: `o${i}`, date: `d${i}`, state: i < 9 ? "present" as const : i < 50 ? "absent" as const : "no_data" as const })) },
  },
}

beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(leadsAPI, "here").mockResolvedValue({ leads: [], total: 0, finder: { status: "done" } }) })

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter><AnswerView c={C} caseId="c1" runId="r1" selectionId="s1" members={[{ type: "financial_transaction", id: "x" }]} onAsk={() => undefined} /></MemoryRouter></QueryClientProvider>)
}

describe("the answer, as designed (screen 5)", () => {
  it("says the level with what it means and its numbers", () => {
    show()
    const a = screen.getByRole("region", { name: "The answer" })
    expect(within(a).getByText("Probable link")).toBeTruthy()
    expect(within(a).getByText("well above chance, but not proven")).toBeTruthy()
    expect(within(a).getByText(/Together on 2 of 3 deposit days/)).toBeTruthy()
  })

  it("defines the relation for these phones and draws one labelled tile per event day, ordinary days counted with no data apart", () => {
    show()
    const d = screen.getByRole("region", { name: "The evidence, day by day" })
    expect(within(d).getByText(/Marisol Teague's phone \(Phone 2\) and Dorian Pell's phone \(Phone 3\)/)).toBeTruthy()
    expect(within(d).getByText("The 3 check deposit days · from the financial records · Together on 2 of 3")).toBeTruthy()
    const tiles = within(within(d).getByRole("list", { name: "The days asked about" })).getAllByRole("button")
    expect(tiles).toHaveLength(3)
    expect(tiles[0].textContent).toContain("Check 2201 · $1,940.00")
    expect(tiles[0].textContent).toContain("Together")
    expect(tiles[0].textContent).toContain("7:10 PM to 8:25 PM")
    expect(tiles[2].getAttribute("data-outcome")).toBe("no_data")
    expect(within(d).getByText("Together on 9, apart on 41, no location data on 2.")).toBeTruthy()
    expect(within(d).getAllByRole("listitem", { name: /: No location data$/ })).toHaveLength(2)
    expect(within(d).getByText(/Phone 2 · Marisol Teague/)).toBeTruthy()
  })

  it("asks the innocent explanations as questions, with Ruled out, Counts for less and Not known, and a way to record a case fact", async () => {
    const add = vi.spyOn(corroborateAPI, "addFact").mockResolvedValue({ id: "f1" })
    show()
    const s = screen.getByRole("region", { name: "Innocent explanations Loupe tested" })
    expect(within(s).getByText("They work together, so of course they meet.")).toBeTruthy()
    expect(within(s).getByText("Ruled out")).toBeTruthy()
    expect(within(s).getByText("Counts for less")).toBeTruthy()
    const w = screen.getByRole("region", { name: "What would change the answer" })
    expect(within(w).getByText(/Mon 14 Mar 2024: Dorian Pell's phone has no locations that day, so it counts neither way. If anything in the case shows them together that day, this becomes 3 of 3./)).toBeTruthy()
    fireEvent.click(within(w).getByRole("button", { name: "Record it" }))
    fireEvent.click(within(w).getByRole("button", { name: "Save" }))
    await waitFor(() => expect(add).toHaveBeenCalledWith("c1", expect.objectContaining({ kind: "live_together", people: ["person:m", "person:d"], run_id: "r1" })))
    expect(await within(w).findByText(/Recorded under your name/)).toBeTruthy()
  })
})

describe("the question's people", () => {
  it("adds someone known only by a phone, with no dossier (live 26 Nov: the Corwen Street demo has no dossiers)", async () => {
    const { QuestionSentence } = await import("./QuestionSentence")
    vi.spyOn(corroborateAPI, "preview").mockResolvedValue({ questions: [{ kind: "together", text: "t", count: 1, count_words: "", chips: {} }], joined: { people: [], instances: ["a", "b"] } } as never)
    vi.spyOn(corroborateAPI, "people").mockResolvedValue({ people: [
      { key: "person:m", label: "Marisol Teague", dossier: false, phones: ["Phone 2"], accounts: 0 },
      { key: "person:d", label: "Dorian Pell", dossier: false, phones: ["Phone 3"], accounts: 1 }] })
    const onAsk = vi.fn()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><QuestionSentence caseId="c1" members={[{ type: "financial_transaction", id: "t1" }]} sourceLabel="" skipped={[]} busy={false} onAsk={onAsk} /></MemoryRouter></QueryClientProvider>)
    await waitFor(() => expect(screen.getByTestId("question-sentence").textContent).toBe("Were these people together on the 2 days you chose?"))
    fireEvent.click(screen.getByRole("button", { name: /Change the people/ }))
    fireEvent.click(await screen.findByRole("button", { name: "+ Marisol Teague · Phone 2" }))
    fireEvent.click(screen.getByRole("button", { name: "+ Dorian Pell · Phone 3" }))
    expect(screen.getByTestId("question-sentence").textContent).toBe("Were Marisol Teague and Dorian Pell together on the 2 days you chose?")
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    expect(onAsk.mock.calls[0][0].chips.people).toEqual(["person:m", "person:d"])
  })
})

describe("next steps are computed from the result (COMMON rule 4)", () => {
  it("ranks the uncovered day first, then their messages on those days, the open explanation, other people, the map", () => {
    const steps = nextSteps(C, "c1")
    expect(steps.map((s) => s.title)).toEqual([
      "Fill the gap on Mon 14 Mar 2024", "Read what they said to each other on those days", "Settle whether they live together",
      "Ask about Priya Halloran on those days", "See where they met", "Test whether this happens every time"])
    expect(steps[0].to).toBe("/cases/c1/timeline?window=2024-03-14..2024-03-14")
    expect(steps[1].why).toBe("31 calls, messages or e-mails between Marisol Teague and Dorian Pell on 2 of the 3 days asked about.")
    expect(steps[3].ask?.chips.people).toEqual(["person:m", "person:d", "person:p"])
  })

  it("offers no step whose data the result does not hold", () => {
    const bare: Corroboration = { ...C, grid: [], not_in_pattern: [], checks: [{ check: "household", outcome: "weighed_low", words: "" }], days: { ...C.days!, tiles: [tile(days[0], "present", "x")] } }
    expect(nextSteps(bare, "c1").map((s) => s.title)).toEqual(["Test whether this happens every time"])
    expect(changes(bare)).toEqual([])
    expect(innocentExplanations(bare)[0].pill).toBe("Counts for less")
  })

  it("reads the question as a sentence per kind", () => {
    expect(template("together", 2).parts.join("")).toBe("Were {who} {rel} on {events}?")
    expect(template("connected", 1).parts.join("")).toBe("Is {who} {rel} to the others on {events}?")
    expect(template("in_contact", 1).parts.join("")).toBe("Was {who} {rel} on {events}?")
  })
})
