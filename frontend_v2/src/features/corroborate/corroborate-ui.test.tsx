import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LookIntoButton } from "@/features/relations/LookIntoButton"
import { setSwitch } from "@/lib/ui-switches"
import { corroborateAPI, type Preview } from "./api"
import { CorroborateTray } from "./CorroborateTray"
import { getSelection } from "./selection-store"
import { memberFromElement, isTyping } from "./item-target"

const preview: Preview = {
  members: 3, selected: 3,
  scope: { active: false, words: [], outside: {}, outside_total: 0, no_time: 0, anchors: null, anchors_date_only: 0, kept: null },
  left_out: { count: 1, examples: ["x"] },
  taken: { people: [{ key: "kell", label: "Kell", count: 2 }, { key: "okafor", label: "Okafor", count: 1 }], times: { from: "2026-05-18", to: "2026-05-19", dated: 3, days: 2, undated: 0 }, places: [], items: [{ type: "financial_transaction", count: 3, words: "3 payments" }] },
  questions: [
    { kind: "in_contact", text: "Were Kell and Okafor in contact around 2026-05-18 to 2026-05-19?", count: 2, count_words: "2 people", chips: { when: "2026-05-18 to 2026-05-19", nights: "2 days", who: "Kell and Okafor", what: "calls, messages, payments", compare_with: "the same hours on other days of the period" } },
    { kind: "who_else", text: "Who else is connected to these?", count: 3, count_words: "3 items", chips: { when: "w", nights: "n", who: "w", what: "w", compare_with: "everyone else in the case" } },
  ],
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/cases/c1/ledger"]}>
    <Routes><Route path="/cases/:id/ledger" element={<>{ui}<CorroborateTray /></>} /><Route path="/cases/c1/relations/g9" element={<p>result page</p>} /></Routes>
  </MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); setSwitch("corroborate-v2", true) })

describe("Corroborate from a selection", () => {
  it("adds the choice to the selection, shows the whole count, drafts the question and hands off the whole set", async () => {
    vi.spyOn(corroborateAPI, "preview").mockResolvedValue(preview)
    const create = vi.spyOn(corroborateAPI, "run").mockResolvedValue({ group: { id: "g9", member_count: 3, left_out: 0 } })
    wrap(<LookIntoButton caseId="c1" surface="financial" group={{ group_type: "financial_selection", how: {}, words: "Marsh's Pocketwire payments", members: [1, 2, 3].map((n) => ({ type: "financial_transaction" as const, id: `p${n}` })) }} />)
    fireEvent.click(screen.getByRole("button", { name: "Corroborate" }))
    expect(getSelection("c1")).toHaveLength(1)
    await screen.findByText(/What Loupe takes from your 3 items/)
    expect(screen.getByText(/1 chosen items are not in this case/)).toBeTruthy()
    expect(screen.getByText("Your question: Were Kell and Okafor in contact around 2026-05-18 to 2026-05-19?")).toBeTruthy()
    fireEvent.change(screen.getByDisplayValue("the same hours on other days of the period"), { target: { value: "ordinary Fridays" } })
    fireEvent.click(screen.getAllByRole("button", { name: "Corroborate" }).at(-1)!)
    await waitFor(() => expect(create).toHaveBeenCalled())
    const body = create.mock.calls[0][1]
    expect(body.members).toHaveLength(3)
    expect((body.question as { chips: { compare_with: string } }).chips.compare_with).toBe("ordinary Fridays")
    await screen.findByText("result page")
  })

  it("shows each part of the selection as a chip with its count and screen, and removes one", () => {
    vi.spyOn(corroborateAPI, "preview").mockResolvedValue(preview)
    wrap(<LookIntoButton caseId="c1" surface="financial" items={[{ target_type: "financial_transaction", target_id: "p1", target_label: "Payment 1" }]} />)
    fireEvent.click(screen.getByRole("button", { name: "Corroborate" }))
    fireEvent.click(screen.getAllByRole("button", { name: "Cancel" })[0])
    expect(screen.getByText(/1 item selected/)).toBeTruthy()
    expect(screen.getByText(/1 from the ledger/)).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Remove Payment 1" }))
    expect(getSelection("c1")).toEqual([])
  })
})

describe("naming an item for right-click and C", () => {
  it("reads the type and id from the item under the pointer, and never fires while typing", () => {
    document.body.innerHTML = '<table><tr data-corro="financial_transaction:abc:1" data-corro-label="Pay"><td><b id="x">cell</b></td></tr></table><input id="i">'
    expect(memberFromElement(document.getElementById("x"))).toEqual({ type: "financial_transaction", id: "abc:1", label: "Pay" })
    expect(memberFromElement(document.body)).toBeNull()
    expect(isTyping(document.getElementById("i"))).toBe(true)
    expect(isTyping(document.getElementById("x"))).toBe(false)
  })
})
