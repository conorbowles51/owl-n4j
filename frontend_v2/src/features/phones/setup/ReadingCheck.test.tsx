import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { Reading, ReadingExamples } from "../review/readings.api"
import { coverage, readingsMark, settleTitle } from "./setup-words"

/** Phones › Set up, the reading check (screen 6): a plain sentence with what changes if wrong, examples side by
 * side (the report's own fields beside what Loupe shows), Looks right held until every kind has been on screen,
 * and progress as readings checked and share of records covered. Synthetic data. */
const api = vi.hoisted(() => ({ examples: vi.fn(), confirm: vi.fn(), correct: vi.fn(), correctionPreview: vi.fn(), confirmKind: vi.fn() }))
vi.mock("../review/readings.api", () => ({ readingsAPI: api }))
vi.mock("@/lib/ux-events", () => ({ trackUx: vi.fn() }))

import { loupeShows, reportLines } from "./example-words"
import { ReadingCheck } from "./ReadingCheck"

function reading(over: Partial<Reading>): Reading {
  return {
    id: "r1", extraction_id: "e1", phone: "Phone 1", type_name: "DeviceConnectivity", type_words: "device connectivities",
    rule_id: "DeviceConnectivity.event_time", part: "event_time",
    sentence: "When Phone 1 connected to another device, the time Loupe puts on the timeline is when the connection started.",
    if_wrong: "If this is wrong, these records sit at the wrong time on the timeline and in every check of when the phone was in use.",
    records: 321, status: "open", origin: null, resolved_by: null, resolved_at: null, reason: null, reason_kind: null, note: null,
    choices: [{ id: "time:none", label: "This is not when it happened" }], ...over,
  }
}

const EXAMPLES: ReadingExamples = {
  id: "r1", records: 321, apps_not_shown: 0,
  kinds: [
    { id: "timed", label: "A typical record", record_uid: "u1", count: 300, number: 1,
      example: { record_uid: "u1", type_words: "device connectivity", report_type: "DeviceConnectivity", kind: null, direction: null, app: null,
        instant: "2024-03-11T21:04:17Z", text: null, subject: null, title: "Corwen-Front-Desk", deleted_state: "Intact", parties: [],
        times: [{ field: "time stamp", report_field: "TimeStamp", instant: "2024-03-11T21:04:17Z", original_text: "2024-03-11 21:04:17", is_event_time: true, mapped_by_this: true }] } },
    { id: "untimed", label: "A record with no time", record_uid: "u2", count: 21, number: 2,
      example: { record_uid: "u2", type_words: "device connectivity", report_type: "DeviceConnectivity", kind: null, direction: null, app: null,
        instant: null, text: null, subject: null, title: "AirPods", deleted_state: "Intact", parties: [],
        times: [{ field: "time stamp", report_field: "TimeStamp", instant: null, original_text: null, is_event_time: true, mapped_by_this: true }] } },
  ],
}

function view(items: Reading[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <ReadingCheck caseId="case-1" extraction="e1" label="Phone 1" items={items} zone="UTC" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}

describe("Set up: checking how the system read a phone", () => {
  beforeEach(() => {
    api.examples.mockResolvedValue(EXAMPLES)
    api.confirm.mockResolvedValue({ decision_id: "d", status: "confirmed", reason: "x", reason_kind: "standard", resolved_by: "Bea" })
    api.correctionPreview.mockResolvedValue({ records: 0, without: null, phones: [], words: null })
  })
  afterEach(() => vi.clearAllMocks())

  it("shows the reading as a plain sentence with what changes if it is wrong, and no report names in it", async () => {
    view([reading({})])
    expect(await screen.findByText(/^When Phone 1 connected to another device/)).toBeInTheDocument()
    expect(screen.getByText(/^If this is wrong, these records sit at the wrong time/)).toBeInTheDocument()
    expect(screen.getByText(/affects 321 records/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Looks right" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Not right" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Skip for now" })).toBeInTheDocument()
  })

  it("puts each example's report fields beside what Loupe shows", async () => {
    view([reading({})])
    await screen.findAllByText("Loupe shows")
    const pre = document.querySelectorAll("pre")
    expect(pre[0].textContent).toBe("DeviceConnectivity\nTimeStamp  2024-03-11 21:04:17\nName  Corwen-Front-Desk")
    expect(pre[1].textContent).toContain("TimeStamp  (empty)")
    expect(screen.getByText(/^Time not recorded: listed at the end, never placed on the timeline\./)).toBeInTheDocument()
    expect(loupeShows(EXAMPLES.kinds[0], "UTC")).toMatch(/^Placed at .*2024.*shown at that time on the timeline\.$/)
    expect(reportLines(EXAMPLES.kinds[1])[0]).toBe("DeviceConnectivity")
  })

  it("sends Looks right with every kind that was on screen, under the person's name", async () => {
    view([reading({}), reading({ id: "r2", records: 10, sentence: "Loupe reads each of Phone 1’s connections to other devices as a record of its own kind, outside the conversations." })])
    await screen.findAllByText("Loupe shows")
    const yes = screen.getByRole("button", { name: "Looks right" })
    await waitFor(() => expect(yes).not.toBeDisabled())
    fireEvent.click(yes)
    await waitFor(() => expect(api.confirm).toHaveBeenCalledWith("case-1", "r1", { viewed: ["timed", "untimed"], opened: ["timed", "untimed"], expected_status: "open" }))
    expect(await screen.findByText(/Saved under your name: reading 1 looks right/)).toBeInTheDocument()
  })

  it("asks for a choice and a reason before a correction is saved", async () => {
    view([reading({})])
    await screen.findAllByText("Loupe shows")
    fireEvent.click(screen.getByRole("button", { name: "Not right" }))
    fireEvent.click(screen.getByRole("button", { name: "This is not when it happened" }))
    const save = screen.getByRole("button", { name: "Save correction" })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Your reason/), { target: { value: "the examiner's notes say so" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.correct).toHaveBeenCalledWith("case-1", "r1", expect.objectContaining({ choice: "time:none", reason: "the examiner's notes say so", scope: "this_phone" })))
  })

  it("counts progress as readings checked and the share of records they cover", () => {
    const items = [reading({ records: 300, status: "confirmed" }), reading({ id: "r2", records: 100 })]
    expect(coverage(items)).toEqual({ readings: 2, checked: 1, percent: 75 })
    view(items)
    expect(screen.getByText("1 of 2 checked")).toBeInTheDocument()
    expect(screen.getByText("75% of records covered")).toBeInTheDocument()
  })

  it("gives investigators a plain mark instead of the queue", () => {
    expect(readingsMark([reading({}), reading({ id: "r2", status: "confirmed" })]).words).toMatch(/^1 of 2 readings of this phone are not checked yet/)
    expect(readingsMark([reading({ status: "confirmed" })])).toEqual({ words: "Every reading of this phone has been checked by a person.", checked: true })
    expect(settleTitle("Phone 1", 3)).toBe("Phone 1: 3 things to settle")
    expect(settleTitle("Phone 2", 0)).toBe("Phone 2: nothing to settle")
  })
})
