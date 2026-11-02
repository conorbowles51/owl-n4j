import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { dispatchKey, resetKeymapForTest } from "@/lib/keymap"
import type { Reading, ReadingExamples, ReadingQueue } from "./readings.api"

/** RQ-1, RQ-2, RQ-3 on the page (02 6.8; 07 J-8): plain sentences, Looks right held until every kind is viewed,
 * and a confirmation shown with its standard reason under the person's name. Synthetic data. */
const api = vi.hoisted(() => ({
  list: vi.fn(),
  examples: vi.fn(),
  progress: vi.fn(),
  confirm: vi.fn(),
  correct: vi.fn(),
}))
vi.mock("./readings.api", () => ({ readingsAPI: api }))
vi.mock("@/lib/ux-events", () => ({ trackUx: vi.fn() }))

import PhoneReviewPage from "./PhoneReviewPage"

function reading(over: Partial<Reading>): Reading {
  return {
    id: "r1", extraction_id: "e1", phone: "C1", type_name: "InstantMessage", type_words: "instant messages",
    rule_id: "InstantMessage.role.From", part: "role",
    sentence: "On C1, instant messages: the party marked from is the sender. Affects 41,233 instant messages.",
    records: 41233, status: "open", origin: "Mapped by the system, not yet confirmed", resolved_by: null,
    resolved_at: null, reason: null, reason_kind: null, note: null,
    choices: [{ id: "role:recipient", label: "The sender is the other party" }], ...over,
  }
}

const QUEUE: ReadingQueue = {
  case_id: "case-1", total: 2, open: 2, checked: 0,
  items: [reading({}), reading({ id: "r2", rule_id: "Call.event_time", part: "event_time", type_name: "Call",
    sentence: "On C1, calls: the time shown as when each call happened is its time stamp. Affects 1,657 calls.", records: 1657, choices: [] })],
}

const EXAMPLES: ReadingExamples = {
  id: "r1", records: 41233, apps_not_shown: 0,
  kinds: ["Incoming", "Outgoing"].map((label, i) => ({
    id: `direction:${label.toLowerCase()}`, label, record_uid: `u${i}`, count: 10, number: i + 1,
    example: { record_uid: `u${i}`, type_words: "instant message", kind: "message", direction: label.toLowerCase(), app: "SyntheticApp",
      instant: "2023-03-14T19:07:12Z", text: "synthetic text", subject: null, title: null, deleted_state: "Intact",
      parties: [{ role: "sender", name: "Synthetic A", identifier: null, is_owner: false, implicit_owner: false, mapped_by_this: true }],
      times: [] },
  })),
}

function page(entry = "/cases/case-1/phone-review") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/cases/:id/phone-review" element={<PhoneReviewPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

describe("Needs a decision, readings group", () => {
  beforeEach(() => {
    resetKeymapForTest()
    api.list.mockResolvedValue(QUEUE)
    api.examples.mockResolvedValue(EXAMPLES)
    api.progress.mockResolvedValue({ phones: [] })
  })
  afterEach(() => vi.clearAllMocks())

  it("lists readings as plain sentences, most records first, with no field names (RQ-1)", async () => {
    page()
    await screen.findByRole("heading", { name: "Needs a decision" })
    const items = await screen.findAllByText(/^On C\d, .+: .+\. Affects [\d,]+ /)
    const counts = items.map((e) => Number((e.textContent ?? "").match(/Affects ([\d,]+)/)![1].replace(/,/g, "")))
    expect(counts).toEqual([...counts].sort((a, b) => b - a))
    const body = document.body.textContent ?? ""
    expect(body).not.toMatch(/\b(TimeStamp|IsPhoneOwner|InstantMessage|role\.From|event_time)\b/)
    expect(screen.getAllByText(/Mapped by the system, not yet confirmed/).length).toBeGreaterThan(0)
  })

  it("opens on the reading a record panel link names (07 J-8b)", async () => {
    page("/cases/case-1/phone-review?reading=r2")
    await waitFor(() => expect(api.examples).toHaveBeenCalledWith("case-1", "r2"))
    expect(await screen.findByText(/^On C1, calls: /)).toBeInTheDocument()
    expect(screen.queryByRole("group", { name: /What is wrong/ })).not.toBeInTheDocument()
  })

  it("a Not right link opens the choices on that reading", async () => {
    page("/cases/case-1/phone-review?reading=r1&answer=not-right")
    await screen.findByRole("button", { name: "The sender is the other party" })
  })

  it("opens on the first reading still needing a decision when earlier ones are decided", async () => {
    api.list.mockResolvedValue({ ...QUEUE, open: 1, checked: 1, items: [reading({ status: "confirmed", resolved_by: "Synthetic Reviewer",
      resolved_at: "2026-11-02T09:00:00Z", reason_kind: "standard", origin: null, reason: "Confirmed on the review screen" }),
      reading({ id: "r2", rule_id: "InstantMessage.role.To", records: 41233 })] })
    page()
    await waitFor(() => expect(api.examples).toHaveBeenCalledWith("case-1", "r2"))
    const ex = await screen.findAllByRole("button", { name: /^Example \d+/ })
    ex.forEach((b) => fireEvent.click(b))
    await screen.findByText("2 of 2 kinds viewed")
    expect(await screen.findByRole("button", { name: /Looks right/ })).toBeEnabled()
  })

  it("holds Looks right until every kind is viewed, then confirms with the standard reason (RQ-2, RQ-3)", async () => {
    api.confirm.mockImplementation(async () => {
      api.list.mockResolvedValue({ ...QUEUE, open: 1, checked: 1, items: [reading({ status: "confirmed", resolved_by: "Synthetic Reviewer",
        resolved_at: "2026-11-02T09:00:00Z", reason_kind: "standard", origin: null,
        reason: "Confirmed on the review screen after viewing 2 examples across 2 kinds" }), QUEUE.items[1]] })
      return { decision_id: "d1", status: "confirmed", reason: "x", reason_kind: "standard", resolved_by: "Synthetic Reviewer" }
    })
    page()
    const looks = await screen.findByRole("button", { name: /Looks right/ })
    expect(looks).toBeDisabled()
    const ex = await screen.findAllByRole("button", { name: /^Example \d+/ })
    expect(ex).toHaveLength(2)
    fireEvent.click(ex[0])
    expect(looks).toBeDisabled()
    fireEvent.click(ex[1])
    await screen.findByText("2 of 2 kinds viewed")
    expect(looks).toBeEnabled()
    dispatchKey(new KeyboardEvent("keydown", { key: "y" }))
    await waitFor(() => expect(api.confirm).toHaveBeenCalledWith("case-1", "r1",
      { viewed: ["direction:incoming", "direction:outgoing"], opened: ["direction:incoming", "direction:outgoing"], note: undefined, expected_status: "open" }))
    await screen.findByText(/Confirmed by Synthetic Reviewer on 2 November 2026\. Standard reason: Confirmed on the review screen after viewing 2 examples across 2 kinds/)
    dispatchKey(new KeyboardEvent("keydown", { key: "x" }))
    await screen.findByRole("button", { name: "The sender is the other party" })
  })

  it("a correction needs the person's reason and shows re-reading progress", async () => {
    api.correct.mockResolvedValue({ decision_id: "d2", status: "corrected", scope: ["C1"], extraction_ids: ["e1"], choice: "x" })
    api.progress.mockResolvedValue({ phones: [{ extraction_id: "e1", phone: "C1", state: "re-reading", records_total: 41233, records_done: 12000, seconds_left: 40 }] })
    page()
    fireEvent.click(await screen.findByRole("button", { name: /Not right/ }))
    fireEvent.click(screen.getByRole("button", { name: "The sender is the other party" }))
    const save = screen.getByRole("button", { name: "Save correction" })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Your reason/), { target: { value: "the far end sent these" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.correct).toHaveBeenCalledWith("case-1", "r1",
      { choice: "role:recipient", reason: "the far end sent these", scope: "this_phone", note: undefined, expected_status: "open" }))
    await screen.findByText(/Re-reading 41,233 records on C1: 12,000 done, about 40 s left\. Screens show the earlier reading until this finishes\./)
  })
})
