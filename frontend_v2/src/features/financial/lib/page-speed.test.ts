import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { flushPageViews, recordPageView, whenSettled } from "./page-speed"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockResolvedValue({ accepted: 1 })
})
afterEach(() => {
  flushPageViews()
  vi.useRealTimers()
})

describe("page speed", () => {
  it("batches views and posts them once, fire-and-forget", () => {
    vi.useFakeTimers()
    recordPageView({ page: "financial/ledger", method: "VIEW", case_id: "c1", ms: 812.6 })
    recordPageView({ page: "financial/overview", method: "LOAD", case_id: "c1", ms: 2400 })
    expect(fetchAPI).not.toHaveBeenCalled()
    vi.advanceTimersByTime(5000)
    expect(fetchAPI).toHaveBeenCalledTimes(1)
    const [url, options] = vi.mocked(fetchAPI).mock.calls[0]
    expect(url).toBe("/api/request-speed/page-views")
    expect((options as { body: { views: unknown[] } }).body.views).toEqual([
      { page: "financial/ledger", method: "VIEW", case_id: "c1", ms: 813 },
      { page: "financial/overview", method: "LOAD", case_id: "c1", ms: 2400 },
    ])
  })

  it("a failed post is swallowed", async () => {
    vi.mocked(fetchAPI).mockRejectedValue(new Error("offline"))
    recordPageView({ page: "financial/ledger", method: "VIEW", case_id: null, ms: 5 })
    expect(() => flushPageViews()).not.toThrow()
    await Promise.resolve()
  })

  it("settles only after every request in flight has returned", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    let release: (value: number) => void = () => {}
    const pending = client.fetchQuery({ queryKey: ["financial", "slow"], queryFn: () => new Promise<number>((r) => { release = r }) })
    let settled: number | null | undefined
    void whenSettled(client, { cancelled: false }).then((value) => { settled = value })
    await new Promise((r) => setTimeout(r, 30))
    expect(settled).toBeUndefined()
    release(1)
    await pending
    await new Promise((r) => setTimeout(r, 60))
    expect(typeof settled).toBe("number")
  })

  it("a cancelled view is not timed", async () => {
    const client = new QueryClient()
    const signal = { cancelled: true }
    expect(await whenSettled(client, signal)).toBeNull()
  })
})
