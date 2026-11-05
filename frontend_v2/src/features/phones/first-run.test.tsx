import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { addInParts, PART_SIZE, type CollectClient } from "./collect.api"
import { justFinished, trackBulkAdd, trayJob, type ServerJob } from "./job-list"
import { NEW_MARK_DAYS, newMarksUntil, PHONES_FEATURE_DATE } from "./marks"
import { FirstPhoneCard } from "./summary/FirstPhoneCard"
import { guideAnchor } from "./ui/screen-guide"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
const api = vi.mocked(fetchAPI)

const job = (over: Partial<ServerJob> = {}): ServerJob => ({
  id: "export:1", kind: "export", title: "Export: messages (PDF)", state: "running", step: "Drawing the export", done: 25, total: 100,
  unit: "percent", started_at: "2026-11-05T10:00:00Z", moved_at: "2026-11-05T10:00:10Z", ended_at: null, note: null, error: null,
  reference: "ref", href: null, ...over,
})

describe("New mark window", () => {
  const day = 86_400_000
  it("runs 7 days from the feature date", () => {
    expect(newMarksUntil([])).toBe(Date.parse(PHONES_FEATURE_DATE) + NEW_MARK_DAYS * day)
    expect(newMarksUntil(["2026-10-01T00:00:00Z"])).toBe(Date.parse(PHONES_FEATURE_DATE) + NEW_MARK_DAYS * day)
  })
  it("runs from the case's first phone when that came later", () => {
    expect(newMarksUntil(["2027-02-01T00:00:00Z", "2027-02-03T00:00:00Z", null])).toBe(Date.parse("2027-02-01T00:00:00Z") + NEW_MARK_DAYS * day)
  })
})

describe("guide links", () => {
  it("reads the screen from the address", () => {
    expect(guideAnchor("/cases/c1/conversations")).toBe("read-a-conversation-around-a-date")
    expect(guideAnchor("/cases/c1/phones/e1/records/media")).toBe("first-look-at-a-phone")
    expect(guideAnchor("/cases/c1/financial")).toBeUndefined()
  })
})

describe("tray lines", () => {
  it("keeps true counts and the server's times", () => {
    const t = trayJob(job(), 0)
    expect(t.progress).toMatchObject({ done: 25, total: 100, unit: "percent", startedAt: Date.parse("2026-11-05T10:00:00Z") })
    expect(t.progress.failed).toBeNull()
  })
  it("names a failure and its reference", () => {
    const t = trayJob(job({ state: "failed", error: "The disk is full." }), 0)
    expect(t.error).toBe("The disk is full.")
    expect(t.progress.failed?.referenceId).toBe("ref")
  })
  it("uses the readiness card's words for adding a phone", () => {
    expect(trayJob(job({ kind: "intake", stage: "detecting", counts: {} }), 0).progress.step).toBe("Finding the report documents")
  })
  it("gives a finished job its notice once", () => {
    const done = job({ state: "done" })
    expect(justFinished(new Set(["export:1"]), [done])).toEqual([done])
    expect(justFinished(new Set(), [done])).toEqual([])
  })
})

describe("a bulk add's server record", () => {
  beforeEach(() => api.mockReset())
  it("reports true counts after each part, so a reload keeps them", async () => {
    api.mockResolvedValue({ id: "run1" } as never)
    const report = await trackBulkAdd("c1", "a dossier", "messages", PART_SIZE + 1)
    const client: CollectClient = { add: async (_c, _t, links) => ({ added: links.length, skipped: 0, refused: 0 }) }
    const links = Array.from({ length: PART_SIZE + 1 }, (_, i) => ({ target_type: "phone_record" as const, target_id: String(i), source_anchor: {} }))
    await addInParts(client, "c1", { kind: "dossier", id: "d", label: "A" }, links, { relationship: "unclassified", role: "link", origin: "x" }, undefined,
      (sent, r) => void report(sent, r, sent >= links.length, null))
    const bodies = api.mock.calls.filter((c) => String(c[0]).endsWith("/run1")).map((c) => (c[1] as { body: { sent: number; added: number; finished: boolean } }).body)
    expect(bodies.map((b) => [b.sent, b.finished])).toEqual([[PART_SIZE, false], [PART_SIZE + 1, true]])
    expect(bodies[1].added).toBe(PART_SIZE + 1)
  })
  it("never stops the add when the record cannot be written", async () => {
    api.mockResolvedValueOnce({ id: "run1" } as never).mockRejectedValueOnce(new Error("down"))
    const report = await trackBulkAdd("c1", "a dossier", "messages", 10)
    await expect(report(1, { added: 1, skipped: 0, refused: 0 }, false, null)).resolves.toBeUndefined()
  })
})

describe("first-phone card", () => {
  const show = (path = "/cases/c1/phones") =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={[path]}><FirstPhoneCard caseId="c1" /></MemoryRouter>
      </QueryClientProvider>
    )
  beforeEach(() => api.mockReset())

  it("shows once and saves that it was seen", async () => {
    api.mockImplementation(async (_url: string, o?: { method?: string }) => (o?.method === "PUT" ? { marks: { first_phone_card_seen: "t" } } : { marks: {} }) as never)
    show()
    expect(await screen.findByRole("region", { name: "What each phone screen is for" })).toBeInTheDocument()
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/phones/my-marks/first_phone_card_seen", { method: "PUT" }))
    // still there after the save: it stays for this visit
    expect(screen.getByText("Needs a decision")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Close" }))
    expect(screen.queryByText("Needs a decision")).not.toBeInTheDocument()
  })
  it("stays away once seen, and Help reopens it", async () => {
    api.mockResolvedValue({ marks: { first_phone_card_seen: "t" } } as never)
    const { unmount } = show()
    await waitFor(() => expect(api).toHaveBeenCalled())
    expect(screen.queryByText("Needs a decision")).not.toBeInTheDocument()
    unmount()
    show("/cases/c1/phones?help=phones")
    expect(screen.getByText("Needs a decision")).toBeInTheDocument()
  })
})
