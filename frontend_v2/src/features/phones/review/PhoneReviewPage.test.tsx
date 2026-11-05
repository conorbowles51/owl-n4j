import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
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
  correctionPreview: vi.fn(),
  confirmKind: vi.fn(),
  rechecks: vi.fn(),
  drawRecheck: vi.fn(),
  recordRecheck: vi.fn(),
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

const NO_RECHECKS = { sampled: 0, agrees: 0, disagrees: 0, pending: 0, rate_percent: null, too_few: false, words: "No confirmation has been sampled for a re-check.", min_base: 20, percent: 5, passes: [], items: [] }

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
    api.correctionPreview.mockResolvedValue({ records: 0, without: null, phones: [], words: null })
    api.rechecks.mockResolvedValue(NO_RECHECKS)
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
      { choice: "role:recipient", reason: "the far end sent these", scope: "this_phone", note: undefined, expected_status: "open", expected_empty: 0 }))
    await screen.findByText(/Re-reading 41,233 records on C1: 12,000 done, about 40 s left\. Screens show the earlier reading until this finishes\./)
  })

  const openCorrection = async () => {
    fireEvent.click(await screen.findByRole("button", { name: /Not right/ }))
    fireEvent.click(screen.getByRole("button", { name: "The sender is the other party" }))
    fireEvent.change(screen.getByRole("textbox", { name: /Your reason/ }), { target: { value: "the far end sent these" } })
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }))
  }

  it("a correction that would leave records empty shows the true count, and Cancel writes nothing (07 J-8)", async () => {
    api.correctionPreview.mockResolvedValue({ records: 2140, without: "no sender", phones: [{ extraction_id: "e1", phone: "C1", records: 2140 }], words: "After this change, 2,140 messages will have no sender." })
    page()
    await openCorrection()
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("After this change, 2,140 messages will have no sender.")
    expect(api.correct).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(api.correct).not.toHaveBeenCalled()
  })

  it("Continue sends the count the person agreed to", async () => {
    api.correctionPreview.mockResolvedValue({ records: 2140, without: "no sender", phones: [{ extraction_id: "e1", phone: "C1", records: 2140 }], words: "After this change, 2,140 messages will have no sender." })
    api.correct.mockResolvedValue({ decision_id: "d2", status: "corrected", scope: ["C1"], extraction_ids: ["e1"], choice: "x" })
    page()
    await openCorrection()
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }))
    await waitFor(() => expect(api.correct).toHaveBeenCalledWith("case-1", "r1", expect.objectContaining({ expected_empty: 2140 })))
    expect(api.correctionPreview).toHaveBeenCalledTimes(1)
  })

  const KIND: ReadingQueue = {
    case_id: "case-1", total: 3, open: 2, checked: 1,
    items: [reading({}), reading({ id: "r3", rule_id: "Call.role.From", sentence: "On C1, calls: the party marked from is the caller. Affects 9 calls.", records: 9 }),
      reading({ id: "r4", rule_id: "Chat.role.From", status: "confirmed", resolved_by: "Ann", sentence: "On C1, chats: already confirmed.", records: 1 }),
      reading({ id: "r5", extraction_id: "e2", phone: "C2", rule_id: "Sms.role.From", sentence: "On C2, a different phone.", records: 1 })],
  }

  it("lists every open row of the kind with its examples before the bulk confirm, and sends only those rows (J-8 step 6)", async () => {
    api.list.mockResolvedValue(KIND)
    let release: (value: ReadingExamples) => void = () => undefined
    api.examples.mockImplementation((_c: string, id: string) => id === "r3" ? new Promise((res) => { release = res }) : Promise.resolve(EXAMPLES))
    api.confirmKind.mockImplementation(async () => {
      api.list.mockResolvedValue({ ...KIND, items: KIND.items.map((x) => (x.id === "r1" ? { ...x, status: "confirmed", resolved_by: "Bea" } : x)) })
      return KIND_RESULT
    })
    const KIND_RESULT = { confirmed: [{ id: "r1" }], refused: [{ id: "r3", sentence: "On C1, calls: the party marked from is the caller. Affects 9 calls.", reason: "Ann confirmed this just now. Your view is updated." }], not_listed: 0, resolved_by: "Bea", words: "Confirmed 1 row under your name, each as its own decision. 1 row was refused." }
    page()
    fireEvent.click(await screen.findByRole("button", { name: /Looks right for all 2 rows of this kind on this phone/ }))
    const panel = await screen.findByRole("region", { name: "Every row of this kind" })
    expect(within(panel).getAllByTestId("kind-row")).toHaveLength(2)
    const go = within(panel).getByRole("button", { name: "Looks right for all 2 rows" })
    expect(go).toBeDisabled() // the second row's examples are not on the screen yet
    release(EXAMPLES)
    await waitFor(() => expect(go).toBeEnabled())
    expect(within(panel).getAllByText("Incoming. 10 of the affected records are of this kind.")).toHaveLength(2)
    fireEvent.click(go)
    const kinds = ["direction:incoming", "direction:outgoing"]
    await waitFor(() => expect(api.confirmKind).toHaveBeenCalledWith("case-1", [{ id: "r1", viewed: kinds }, { id: "r3", viewed: kinds }], undefined))
    // the refetch shows the reading confirmed; the outcome stays on the screen until the person closes it
    expect(await screen.findByText(/1 row was refused/)).toBeInTheDocument()
    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(1))
    expect(within(screen.getByRole("list", { name: "Refused rows" })).getByRole("listitem")).toHaveTextContent("Ann confirmed this just now")
  })

  it("offers no bulk confirm for a kind with one open row", async () => {
    page()
    await screen.findByRole("button", { name: /Not right/ })
    expect(screen.queryByRole("button", { name: /rows of this kind/ })).toBeNull()
  })

  it("reports the server's counts and records a second person's result, disagreement needing a note (07 J-8)", async () => {
    api.rechecks.mockResolvedValue({ ...NO_RECHECKS, sampled: 3, agrees: 1, disagrees: 1, pending: 1, too_few: true, words: "1 of 2 checked confirmations disagree. Too few for a rate (under 20 checked). 1 not yet checked.",
      passes: [{ pass_id: "p", task_id: "t", title: "x", seed: 7, percent: 5, eligible: 60, reviewer: "Bea", sampled: 3 }],
      items: [{ task_id: "t", confirmation_id: "c1", phone: "C1", extraction_id: "e1", sentence: "On C1: sampled reading.", first: { by_name: "Ann", reason: "Confirmed on the review screen after viewing 2 examples across 2 kinds" }, result: null, earlier_results: 0, reading_id: "r1", status_now: "confirmed", mine: true, own_confirmation: false }] })
    api.recordRecheck.mockResolvedValue({ left: 0 })
    page()
    expect(await screen.findByText(/^1 of 2 checked confirmations disagree\. Too few for a rate/)).toBeInTheDocument()
    expect(screen.getByText("3 of 60 sampled for Bea (5%, seed 7).")).toBeInTheDocument()
    const row = screen.getByTestId("recheck-row")
    const no = within(row).getByRole("button", { name: "Disagrees" })
    expect(no).toBeDisabled()
    fireEvent.change(within(row).getByRole("textbox", { name: "Re-check note" }), { target: { value: "the far end sent it" } })
    fireEvent.click(no)
    await waitFor(() => expect(api.recordRecheck).toHaveBeenCalledWith("case-1", "t", "c1", false, "the far end sent it"))
  })

  it("a person's own confirmation in a sample offers no result", async () => {
    api.rechecks.mockResolvedValue({ ...NO_RECHECKS, sampled: 1, pending: 1, words: "1 confirmation sampled; none checked yet.",
      items: [{ task_id: "t", confirmation_id: "c1", phone: "C1", extraction_id: "e1", sentence: "On C1: mine.", first: { by_name: "Ann" }, result: null, earlier_results: 0, reading_id: "r1", status_now: "confirmed", mine: true, own_confirmation: true }] })
    page()
    expect(await screen.findByText(/someone else needs to re-check it/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Agrees" })).toBeNull()
  })
})
