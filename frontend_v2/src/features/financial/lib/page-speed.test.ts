import { createElement, type ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { apiRequestsInFlight, fetchAPI } from "@/lib/api-client"
import { flushPageViews, recordPageView, useFinancialViewSpeed, whenSettled } from "./page-speed"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn(), apiRequestsInFlight: vi.fn() }))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockResolvedValue({ accepted: 1 })
  vi.mocked(apiRequestsInFlight).mockReturnValue(0)
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

  it("waits while other API requests are in flight, then posts once at low priority", () => {
    vi.useFakeTimers()
    vi.mocked(apiRequestsInFlight).mockReturnValue(3)
    recordPageView({ page: "financial/ledger", method: "VIEW", case_id: "c1", ms: 900 })
    vi.advanceTimersByTime(5000)
    expect(fetchAPI).not.toHaveBeenCalled()
    vi.advanceTimersByTime(10000)
    expect(fetchAPI).not.toHaveBeenCalled()
    vi.mocked(apiRequestsInFlight).mockReturnValue(0)
    vi.advanceTimersByTime(1000)
    expect(fetchAPI).toHaveBeenCalledTimes(1)
    expect(vi.mocked(fetchAPI).mock.calls[0][1]).toMatchObject({ priority: "low", keepalive: false })
  })

  it("posts after a minute even if the app never goes quiet, and at once on leaving", () => {
    vi.useFakeTimers()
    vi.mocked(apiRequestsInFlight).mockReturnValue(1)
    recordPageView({ page: "financial/ledger", method: "VIEW", case_id: "c1", ms: 900 })
    vi.advanceTimersByTime(5000 + 59000)
    expect(fetchAPI).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(fetchAPI).toHaveBeenCalledTimes(1)
    recordPageView({ page: "financial/trends", method: "LEFT", case_id: "c1", ms: 300 })
    flushPageViews(true)
    expect(fetchAPI).toHaveBeenCalledTimes(2)
    expect(vi.mocked(fetchAPI).mock.calls[1][1]).toMatchObject({ keepalive: true })
  })

  it("leaving posts every queued view, 50 per post", () => {
    vi.useFakeTimers()
    vi.mocked(apiRequestsInFlight).mockReturnValue(1)
    for (let i = 0; i < 19; i++) recordPageView({ page: "financial/ledger", method: "VIEW", case_id: "c1", ms: i })
    for (let i = 0; i < 60; i++) recordPageView({ page: "financial/ledger", method: "VIEW", case_id: "c1", ms: i })
    flushPageViews(true)
    const sizes = vi.mocked(fetchAPI).mock.calls.map(([, o]) => (o as { body: { views: unknown[] } }).body.views.length)
    expect(sizes).toEqual([50, 29])
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

  it("a view left before its data arrives is recorded as LEFT; a shown one by its time", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
    const posted = () => vi.mocked(fetchAPI).mock.calls.flatMap(
      ([, options]) => (options as { body: { views: { page: string; method: string }[] } }).body.views)
    let release: (value: number) => void = () => {}
    void client.fetchQuery({ queryKey: ["financial", "slow"], queryFn: () => new Promise<number>((r) => { release = r }) })
    const view = renderHook(({ page }) => useFinancialViewSpeed("c1", page), { wrapper, initialProps: { page: "financial/ledger" } })
    await new Promise((r) => setTimeout(r, 50))
    view.rerender({ page: "financial/trends" })
    await new Promise((r) => setTimeout(r, 50))
    release(1)
    await new Promise((r) => setTimeout(r, 80))
    view.unmount()
    flushPageViews()
    expect(posted().map((v) => `${v.method} ${v.page}`)).toEqual(["LEFT financial/ledger", "VIEW financial/trends"])
  })

  it("closing the tab mid-load posts LEFT at once", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
    void client.fetchQuery({ queryKey: ["financial", "never"], queryFn: () => new Promise<number>(() => {}) })
    const view = renderHook(() => useFinancialViewSpeed("c1", "financial/ledger"), { wrapper })
    await new Promise((r) => setTimeout(r, 50))
    window.dispatchEvent(new Event("pagehide"))
    const views = vi.mocked(fetchAPI).mock.calls.flatMap(
      ([, options]) => (options as { body: { views: { method: string }[] } }).body.views)
    expect(views.map((v) => v.method)).toEqual(["LEFT"])
    expect((vi.mocked(fetchAPI).mock.calls[0][1] as { keepalive: boolean }).keepalive).toBe(true)
    view.unmount() // already counted: no second LEFT
    flushPageViews()
    expect(vi.mocked(fetchAPI)).toHaveBeenCalledTimes(1)
  })
})
