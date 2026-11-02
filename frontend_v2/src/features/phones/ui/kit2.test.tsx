import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GuideDialog } from "@/components/ui/guide-dialog"
import { JobTray, trayLabel, type TrayJob } from "@/components/ui/job-tray"
import { percentShown, ProgressPanel, stallState, timeLeft, type ProgressState } from "@/components/ui/progress-panel"
import { dispatchKey, resetKeymapForTest } from "@/lib/keymap"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import { addInParts, PART_SIZE, resultSentence, type CollectClient, type CollectLink } from "../collect.api"
import { instantWords, timeOfDay } from "../lib/time-words"
import { participantsLine, partyWords, type PhoneRecordView } from "../types"
import { AddToMenu, orderTargets } from "./AddToMenu"
import { DockedPanel } from "./DockedPanel"
import { PhoneTable } from "./PhoneTable"
import { recordCopyText, RecordPanelContent, usedInWords } from "./RecordPanel"
import { EMPTY_SCOPE, ScopeBar, scopeToSearch, scopeWords, searchToScopeIds, type Scope } from "./ScopeBar"
import { stripSummary, TimeStrip } from "./TimeStrip"

afterEach(() => resetKeymapForTest())

const base: ProgressState = { step: "Counting matching messages on 3 phones", startedAt: 0, movedAt: 0 }

describe("progress panel (07 4.7)", () => {
  it("never invents a time left and never shows 100% before drawn", () => {
    expect(timeLeft({ ...base, done: 0, total: 186787 }, 2000)).toBe("Working out time left (first run of this step)")
    expect(timeLeft({ ...base, done: 98000, total: 186787 }, 10000)).toBe("about 9 s left")
    expect(timeLeft({ ...base, done: 0, total: 1000, lastRateMsPerUnit: 40 }, 500)).toBe("about 40 s left")
    expect(percentShown({ ...base, done: 186787, total: 186787 })).toBe(99)
    expect(percentShown({ ...base, done: 186787, total: 186787, drawn: true })).toBe(100)
  })
  it("one stall rule: still at 3 s, slow with Try again at 10 s; background after its threshold", () => {
    expect(stallState(base, 2999, false).kind).toBe("moving")
    expect(stallState(base, 3000, false).kind).toBe("still")
    expect(stallState(base, 10000, false).kind).toBe("slow")
    expect(stallState(base, 29999, true).kind).toBe("moving")
    expect(stallState(base, 30000, true).kind).toBe("still")
  })
  it("shows after 300 ms with words and true counts; the stall sentences name the step", () => {
    const { rerender } = render(<ProgressPanel progress={{ ...base, done: 98000, total: 186787, unit: "messages", movedAt: 0 }} now={200} />)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
    rerender(<ProgressPanel progress={{ ...base, done: 98000, total: 186787, unit: "messages", movedAt: 400 }} now={500} />)
    expect(screen.getByRole("status")).toHaveTextContent("Counting matching messages on 3 phones98,000 of 186,787 messages")
    rerender(<ProgressPanel progress={{ ...base, movedAt: 0 }} now={4000} />)
    expect(screen.getByRole("status")).toHaveTextContent("Still working on counting matching messages on 3 phones")
    const retry = vi.fn()
    rerender(<ProgressPanel progress={{ ...base, movedAt: 0 }} now={11000} onRetry={retry} />)
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(retry).toHaveBeenCalled()
    rerender(<ProgressPanel background progress={{ step: "Reading records", startedAt: 0, movedAt: 0 }} now={45000} formatClock={() => "3:04:05 PM"} />)
    expect(screen.getByRole("status")).toHaveTextContent("No change on reading records for 45 s. The server is still on this step. Last change at 3:04:05 PM")
  })
  it("a failure names the step with a reference id", () => {
    render(<ProgressPanel progress={{ ...base, failed: { what: "Counting matching messages", referenceId: "ref-7" } }} now={100} onRetry={() => {}} />)
    expect(screen.getByRole("alert")).toHaveTextContent("Counting matching messages stopped. Reference: ref-7.")
  })
})

describe("job tray (07 4.7)", () => {
  const jobs: TrayJob[] = [
    { id: "1", title: "Getting C3 ready", state: "running", progress: { step: "Reading records", done: 12000, total: 71045, unit: "records", startedAt: 0, movedAt: 9000 }, href: "/x", onCancel: () => {}, cancelWords: "the files already checked are kept" },
    { id: "2", title: "Export: messages between A and B", state: "done", progress: { step: "Drawing pages", startedAt: 0, movedAt: 0 }, href: "/y" },
  ]
  it("labels counts and lists each job in words with time left and a link when done", () => {
    expect(trayLabel(jobs)).toBe("Jobs (1 running, 1 done)")
    render(<JobTray jobs={jobs} now={10000} defaultOpen />)
    const list = screen.getByRole("list", { name: "Jobs" })
    expect(list).toHaveTextContent("Reading records: 12,000 of 71,045 records, about 49 s left")
    expect(within(list).getByRole("link", { name: "Open the result" })).toHaveAttribute("href", "/y")
    expect(within(list).getByRole("button", { name: /Cancel \(the files already checked are kept\)/ })).toBeInTheDocument()
  })
})

describe("time strip (07 J-4)", () => {
  const days = [
    { date: "2024-03-03", count: 4 },
    { date: "2024-03-04", count: 0 },
    { date: "2024-03-05", count: null },
    { date: "2024-03-06", count: 12 },
  ]
  it("keeps no data apart from quiet days", () => {
    expect(stripSummary(days, "messages")).toBe("16 messages over 4 days; 1 days with none; 1 days with no data")
  })
  it("arrow keys move a day cursor, Enter goes to the day, and it resizes and collapses", () => {
    const pick = vi.fn()
    render(<TimeStrip days={days} zone="Eastern time (UTC-5)" onPickDay={pick} />)
    const slider = screen.getByRole("slider")
    fireEvent.keyDown(slider, { key: "ArrowRight" })
    fireEvent.keyDown(slider, { key: "ArrowRight" })
    expect(slider).toHaveAttribute("aria-valuetext", "Tuesday, March 5, 2024: no data")
    fireEvent.keyDown(slider, { key: "ArrowRight" })
    fireEvent.keyDown(slider, { key: "Enter" })
    expect(pick).toHaveBeenCalledWith("2024-03-06")
    const sep = screen.getByRole("separator", { name: "Resize the time strip" })
    expect(sep).toHaveAttribute("aria-valuenow", "48")
    fireEvent.keyDown(sep, { key: "ArrowUp" })
    expect(sep).toHaveAttribute("aria-valuenow", "56")
    fireEvent.click(screen.getByRole("button", { name: "Hide time strip" }))
    expect(screen.queryByRole("slider")).toBeNull()
  })
})

describe("scope bar (07 4.5)", () => {
  const scope: Scope = {
    ...EMPTY_SCOPE,
    people: [{ key: "p1", label: "Avery Ashdown" }, { key: "p2", label: "Blair Corwood" }],
    mode: "between",
    phones: [{ id: "x1", label: "C1", index: 0, extractionDate: "2024-05-03" }, { id: "x2", label: "C1", index: 1, extractionDate: "2024-06-01" }],
    window: { from: "1 Jan 2024", to: "31 Mar 2024" },
  }
  it("round-trips through the URL and states the scope in words", () => {
    const ids = searchToScopeIds(scopeToSearch(scope))
    expect(ids).toEqual({ people: ["p1", "p2"], mode: "between", phones: ["x1", "x2"], window: { from: "1 Jan 2024", to: "31 Mar 2024" }, labels: [], kinds: [] })
    expect(scopeWords(scope)).toBe("between Avery Ashdown and Blair Corwood, 1 Jan 2024 to 31 Mar 2024, on 2 phones")
  })
  it("chips are removable, colliding phone labels carry dates, and the count is stated", () => {
    const change = vi.fn()
    render(<ScopeBar scope={scope} onChange={change} count={{ shown: 2236, total: 2236, noun: "messages and calls", unconfirmed: 41 }} restored />)
    expect(screen.getByText("C1 · 3 May")).toBeInTheDocument()
    expect(screen.getByText("C1 · 1 Jun")).toBeInTheDocument()
    expect(screen.getByTestId("result-count")).toHaveTextContent("2,236 messages and calls41 not yet confirmed")
    fireEvent.click(screen.getByRole("button", { name: "Remove Avery Ashdown" }))
    expect(change.mock.calls[0][0].people).toEqual([{ key: "p2", label: "Blair Corwood" }])
    expect(screen.getByRole("status")).toHaveTextContent("Showing your last selection")
  })
})

type Row = { id: string; name: string; calls: number }
const rows: Row[] = Array.from({ length: 1200 }, (_, i) => ({ id: `r${i}`, name: `Person ${String(i).padStart(4, "0")}`, calls: (i * 37) % 101 }))

describe("phone table (07 4.4)", () => {
  it("states the exact total, sorts, resizes by keyboard and selects with keys", () => {
    usePhoneSelection.getState().setCase("t")
    usePhoneSelection.getState().clear()
    usePhoneSelection.getState().focusOn(null)
    render(
      <PhoneTable
        rows={rows}
        total={1200}
        rowId={(r) => r.id}
        noun="contacts"
        label="Contacts"
        columns={[
          { id: "name", header: "Name", width: 200, cell: (r) => r.name, sortValue: (r) => r.name },
          { id: "calls", header: "Calls", width: 100, cell: (r) => r.calls, sortValue: (r) => r.calls },
        ]}
      />
    )
    expect(screen.getByTestId("result-count")).toHaveTextContent("1,200 contacts")
    const grid = screen.getByRole("grid", { name: "Contacts" })
    expect(grid).toHaveAttribute("aria-rowcount", "1201")
    fireEvent.click(screen.getByRole("button", { name: /Calls/ }))
    expect(screen.getByRole("columnheader", { name: /Calls/ })).toHaveAttribute("aria-sort", "ascending")
    const sep = screen.getByRole("separator", { name: "Resize Name column" })
    fireEvent.keyDown(sep, { key: "ArrowRight" })
    expect(sep).toHaveAttribute("aria-valuenow", "216")
    fireEvent.keyDown(grid, { key: "j" })
    fireEvent.keyDown(grid, { key: "J" })
    fireEvent.keyDown(grid, { key: "J" })
    expect(usePhoneSelection.getState().ids).toHaveLength(3)
  })
})

const rec: PhoneRecordView = {
  id: "C1-t0-m4",
  kind: "message",
  typeWords: "Message",
  phone: { id: "x1", label: "C1", index: 0 },
  app: "WhatsApp",
  time: "2024-03-05T20:04:05.000Z",
  zone: "America/New_York",
  direction: "outgoing",
  from: { name: "Avery Ashdown", identifier: "+12015550100", isOwner: true },
  to: [{ name: "Blair Corwood", identifier: "+13025550101" }],
  body: "are we still on for later",
  origin: { state: "unconfirmed", rule: "The From field is read as the sender." },
  badges: ["unconfirmed", "other-phone"],
  usedIn: { findings: 1, dossiers: 1, notes: 0, timeline: 0, labels: 0 },
}

describe("record panel and docked slot (07 4.3, 5)", () => {
  it("words time, both sides and use, and copies the full form with the mark", () => {
    expect(instantWords(rec.time!, rec.zone)).toBe("Tue, Mar 5, 2024, 3:04:05 PM EST")
    expect(timeOfDay(rec.time!, rec.zone, true)).toBe("3:04:05 PM")
    expect(participantsLine(rec)).toBe("Avery Ashdown (+12015550100) → Blair Corwood (+13025550101)")
    expect(partyWords({ name: null, identifier: null, isOwner: true })).toBe("This phone's owner (no number in the report)")
    expect(usedInWords(rec.usedIn)).toBe("In 1 finding, 1 dossier.")
    expect(recordCopyText(rec)).toContain("[Mapped by the system, not yet confirmed]")
  })
  it("the docked panel is not modal: the page behind stays usable and keys still reach it", () => {
    const moved = vi.fn()
    render(
      <div>
        <button type="button" onClick={moved}>
          Next message
        </button>
        <DockedPanel title="Record" open onClose={() => {}}>
          <RecordPanelContent record={rec} onAddTo={() => {}} onCorrect={() => {}} canCorrect={false} correctDisabledReason="A case admin can correct values." />
        </DockedPanel>
      </div>
    )
    expect(screen.getByRole("complementary", { name: "Record" })).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Next message" }))
    expect(moved).toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Correct this value" })).toBeDisabled()
    expect(screen.getByText("A case admin can correct values.")).toBeInTheDocument()
  })
})

describe("Add to… (07 J-12, 6.2)", () => {
  const links: CollectLink[] = Array.from({ length: 12345 }, (_, i) => ({ target_type: "phone_record", target_id: `r${i}`, source_anchor: {} }))
  it("sends in parts of 5,000 and sums added and already-there counts", async () => {
    const calls: number[] = []
    const client: CollectClient = { add: async (_c, _t, part) => (calls.push(part.length), { added: part.length - (calls.length === 1 ? 3 : 0), skipped: calls.length === 1 ? 3 : 0, refused: 0 }) }
    const progress: number[] = []
    const r = await addInParts(client, "c", { kind: "finding", id: "f", label: "Finding 1" }, links, { relationship: "supports", role: "link", origin: "Added from Conversations" }, (d) => progress.push(d))
    expect(calls).toEqual([PART_SIZE, PART_SIZE, 2345])
    expect(progress).toEqual([0, 5000, 10000, 12345])
    expect(resultSentence(r, "messages", { kind: "finding", id: "f", label: "Finding 1" })).toBe("Added 12,342 messages to Finding 1. 3 were already there.")
  })
  it("orders a linked person's dossier first, then recent", () => {
    const t = orderTargets(
      [
        { kind: "dossier", id: "1", label: "Alpha" },
        { kind: "dossier", id: "2", label: "Beta", recent: true },
        { kind: "dossier", id: "3", label: "Gamma", linkedPerson: true },
        { kind: "finding", id: "4", label: "F" },
      ],
      "dossier"
    )
    expect(t.map((x) => x.id)).toEqual(["3", "2", "1"])
  })
  it("c then w opens it on findings; a key-triggered add over 5,000 asks first; the reply states counts", async () => {
    const client: CollectClient = { add: async (_c, _t, part) => ({ added: part.length, skipped: 0, refused: 0 }) }
    render(<AddToMenu caseId="c" links={links} noun="messages" origin="Added from Conversations" client={client} targets={[{ kind: "finding", id: "f", label: "Payments were arranged by phone" }]} onUndo={() => {}} />)
    dispatchKey(new KeyboardEvent("keydown", { key: "c" }), 1000)
    dispatchKey(new KeyboardEvent("keydown", { key: "w" }), 1100)
    const dialog = await screen.findByRole("dialog", { name: "Add 12,345 messages to…" })
    expect(within(dialog).getByRole("alert")).toHaveTextContent("more than 5,000")
    expect(within(dialog).getByText(/Adding in 3 parts\. Nothing is cut\./)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByLabelText(/Payments were arranged by phone/))
    expect(within(dialog).getByRole("button", { name: "Add 12,345 messages" })).toBeDisabled()
    fireEvent.click(within(dialog).getByRole("button", { name: "Yes, add all 12,345" }))
    fireEvent.click(within(dialog).getByRole("button", { name: "Add 12,345 messages" }))
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Added 12,345 messages to Payments were arranged by phone."))
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument()
  })
  it("disabled with the reason when the person may not add", () => {
    render(<AddToMenu caseId="c" links={links.slice(0, 1)} noun="messages" origin="o" client={{ add: vi.fn() }} targets={[]} disabledReason="You can view this case but not change it." />)
    expect(screen.getByRole("button", { name: "Add to…" })).toBeDisabled()
    expect(screen.getByText("You can view this case but not change it.")).toBeInTheDocument()
  })
})

describe("guide dialog (07 9)", () => {
  it("opens from its button and shows the document, with a choice between guides", async () => {
    render(
      <GuideDialog
        trigger="Guide"
        guides={[
          { id: "user", label: "User guide", title: "Phone user guide", url: "/u", directory: "/", heading: "# Phone user guide", prefix: "pg" },
          { id: "check", label: "Checklist", title: "Phone checklist", url: "/c", directory: "/", heading: "# Phone checklist", prefix: "pc" },
        ]}
        preloaded={{ user: "# Phone user guide\n\n## Start here\n\nRead the Phone summary first.", check: "# Phone checklist\n\n1. Add a phone" }}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "Guide" }))
    expect(await screen.findByRole("heading", { name: "Start here" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Checklist" }))
    expect(await screen.findByText("Add a phone")).toBeInTheDocument()
  })
})
