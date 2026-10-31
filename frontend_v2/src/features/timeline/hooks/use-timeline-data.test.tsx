import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { timelineAPI, type TimelineEvent } from "../api"
import { useTimelineData } from "./use-timeline-data"
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../api", () => ({ timelineAPI: { getEvents: vi.fn() } }))
const event: TimelineEvent = {
  key: "graph",
  name: "Transfer",
  type: "Transaction",
  date: "2021-02-08",
  time: null,
  amount: "125.00 USD",
  summary: null,
  notes: null,
  connections: [],
}
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return renderHook(() => useTimelineData({ caseId: "case" }), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  })
}
it("falls back to every graph page when the whole read fails, and removes the graph copy of an added payment", async () => {
  vi.mocked(timelineAPI.getEvents).mockImplementation(async ({ cursor, whole }) => {
    if (whole) throw new ApiError("Server error", 500)
    return cursor
      ? {
          events: [{ ...event, key: "other" }],
          count: 1,
          total: 2,
          next_cursor: null,
        }
      : {
          events: [{ ...event, ledger_transaction_id: "payment" }],
          count: 1,
          total: 2,
          next_cursor: "next",
        }
  })
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("offset=0")
      ? ({
          case_id: "case",
          events: [
            {
              ...event,
              key: "timeline-entry:one",
              source: { kind: "transaction", id: "payment" },
            },
          ],
          next_offset: 1,
        } as never)
      : ({
          case_id: "case",
          events: [
            { ...event, key: "timeline-entry:two", type: "Observation" },
          ],
          next_offset: null,
        } as never)
  )
  const { result } = setup()
  await waitFor(() => expect(result.current.isLoading).toBe(false))
  expect(result.current.events.map((row) => row.key)).toEqual([
    "other",
    "timeline-entry:one",
    "timeline-entry:two",
  ])
  expect(result.current.totalCount).toBe(3)
  expect(result.current.eventTypes).toContain("Observation")
})
it("reports a failed additions read instead of presenting the graph-only subset as complete", async () => {
  vi.mocked(timelineAPI.getEvents).mockResolvedValue({
    events: [event],
    count: 1,
    total: 1,
    next_cursor: null,
  })
  vi.mocked(fetchAPI).mockRejectedValue(Error("Request failed"))
  const { result } = setup()
  await waitFor(() =>
    expect(result.current.error?.message).toBe("Request failed")
  )
  expect(result.current.dataKey).toBeNull()
})
it("stops paging when the load is cancelled, instead of fetching the remaining pages", async () => {
  vi.mocked(timelineAPI.getEvents).mockReset()
  vi.mocked(fetchAPI).mockReset()
  let releaseFirst: () => void = () => {}
  vi.mocked(timelineAPI.getEvents).mockImplementation(
    ({ signal }) =>
      new Promise((resolve, reject) => {
        signal?.addEventListener("abort", () => reject(signal.reason), {
          once: true,
        })
        releaseFirst = () =>
          resolve({ events: [event], count: 1, total: 2, next_cursor: "next" })
      })
  )
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const { unmount } = renderHook(() => useTimelineData({ caseId: "case" }), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  })
  await waitFor(() => expect(timelineAPI.getEvents).toHaveBeenCalledTimes(1))
  const signal = vi.mocked(timelineAPI.getEvents).mock.calls[0][0].signal
  expect(signal).toBeInstanceOf(AbortSignal)
  unmount()
  await client.cancelQueries({ queryKey: ["timeline", "case"] })
  expect(signal?.aborted).toBe(true)
  releaseFirst()
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(timelineAPI.getEvents).toHaveBeenCalledTimes(1)
  expect(fetchAPI).not.toHaveBeenCalled()
})

it("loads the whole Timeline in one request when the server gives it", async () => {
  vi.mocked(timelineAPI.getEvents).mockReset()
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(timelineAPI.getEvents).mockResolvedValue({
    events: [event, { ...event, key: "other" }],
    count: 2,
    total: 2,
    next_cursor: null,
  })
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "case",
    events: [],
    next_offset: null,
  } as never)
  const { result } = setup()
  await waitFor(() => expect(result.current.isLoading).toBe(false))
  expect(timelineAPI.getEvents).toHaveBeenCalledTimes(1)
  expect(vi.mocked(timelineAPI.getEvents).mock.calls[0][0]).toMatchObject({ whole: true })
  expect(result.current.events.map((row) => row.key)).toEqual(["graph", "other"])
  expect(result.current.totalCount).toBe(2)
})
it("says the Timeline is too large when the server refuses the whole read, without paging", async () => {
  vi.mocked(timelineAPI.getEvents).mockReset()
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(timelineAPI.getEvents).mockRejectedValue(new ApiError("too many", 413))
  const { result } = setup()
  await waitFor(() =>
    expect(result.current.error?.message).toBe(
      "The Timeline is too large to load completely. Narrow the case scope."
    )
  )
  expect(timelineAPI.getEvents).toHaveBeenCalledTimes(1)
})
