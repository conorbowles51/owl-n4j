import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

/** 07 5 Media (M-5): batch reading of a Media scope with true counts in the job tray. Synthetic data only. */
const api = vi.hoisted(() => ({ describeDeriveBatch: vi.fn(), createDeriveBatch: vi.fn(), getDeriveBatches: vi.fn(), cancelDeriveBatch: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
import { BatchReading } from "./BatchReading"
import { batchJob } from "./batch-words"

const facts = (kind: string, eligible: number) => ({ kind, in_scope: eligible + 3, eligible, noun: kind === "transcript" ? "voice notes and videos" : "images", left_out: { already_read: 1, not_in_production: 2, empty_placeholder: 0 } })
const batch = (over: object) => ({ id: "b1", kind: "transcript", scope_words: "this phone", total: 3, done: 0, failed: 0, queued: 3, running: 0, cancelled: false, cancelled_count: 0, state: "running", created_at: "2026-11-03T08:00:00Z", first_started_at: null, last_finished_at: null, noun: "voice notes and videos", left_out: {}, ...over })

describe("Batch reading (M-5)", () => {
  it("states the true number it would read and what it leaves out, starts it, and shows it in the job tray", async () => {
    api.describeDeriveBatch.mockImplementation((_f: unknown, kind: string) => Promise.resolve(facts(kind, kind === "transcript" ? 3 : 0)))
    api.getDeriveBatches.mockResolvedValueOnce({ case_id: "c", items: [] }).mockResolvedValue({ case_id: "c", items: [batch({ done: 1, running: 1, queued: 1, first_started_at: "2026-11-03T08:00:01Z", last_finished_at: "2026-11-03T08:00:20Z" })] })
    api.createDeriveBatch.mockResolvedValue(batch({}))
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BatchReading caseId="c" filter={{ case_id: "c", phones: ["e1"] }} scopeWords="this phone" />
      </QueryClientProvider>,
    )
    const go = await screen.findByRole("button", { name: "Transcribe all 3 voice notes and videos in this scope" })
    expect(screen.getByText("Left out: 1 already read or waiting, 2 not in the production.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Read text in all/ })).toBeNull() // no image in scope to read
    fireEvent.click(go)
    await waitFor(() => expect(api.createDeriveBatch).toHaveBeenCalledWith({ case_id: "c", phones: ["e1"] }, "transcript", "this phone"))
    fireEvent.click(await screen.findByRole("button", { name: "Jobs (1 running)" }))
    const tray = await screen.findByRole("list", { name: "Jobs" })
    expect(within(tray).getByText("Transcribing 3 voice notes and videos (this phone)")).toBeInTheDocument()
    expect(within(tray).getByText(/^Read: 1 of 3 voice notes and videos, /)).toBeInTheDocument()
  })

  it("words a stopped batch and a finished one with failures", () => {
    const stopped = batchJob(batch({ state: "cancelled", cancelled: true, done: 2, cancelled_count: 1, queued: 0 }) as never)
    expect(stopped.state).toBe("failed")
    expect(stopped.title).toBe("Transcribing 3 voice notes and videos (this phone): stopped by request after 2 of 3; 1 not started were removed; finished readings are kept")
    const done = batchJob(batch({ state: "done", done: 2, failed: 1, queued: 0 }) as never)
    expect(done.state).toBe("done")
    expect(done.title).toBe("Transcribing 3 voice notes and videos (this phone): 1 could not be read")
  })
})
