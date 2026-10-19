import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { timelineAPI, type TimelineEvent } from "../api"
import { useTimelineData } from "./use-timeline-data"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
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
it("loads every graph and curated page and removes the graph copy of an added payment", async () => {
  vi.mocked(timelineAPI.getEvents).mockImplementation(async ({ cursor }) =>
    cursor
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
  )
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
