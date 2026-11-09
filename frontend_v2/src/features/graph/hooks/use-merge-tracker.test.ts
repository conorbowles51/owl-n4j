import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { graphAPI } from "../api"
import { useMergeTracker } from "./use-merge-tracker"

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal("WebSocket", undefined)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const run = async (searchPending: boolean | null) => {
  vi.spyOn(graphAPI, "getEngineJob").mockResolvedValue({ status: "completed", progress: 1 } as never)
  vi.spyOn(graphAPI, "getMergeJob").mockResolvedValue({
    id: "m1", status: "completed", merged_entity_key: "new", recycled_source_keys: ["a", "b"],
    source_entity_keys: ["a", "b"], error_message: null, search_pending: searchPending,
  })
  const { result } = renderHook(() => useMergeTracker())
  act(() => result.current.startTracking("e1", "m1", ["a", "b"]))
  await act(async () => { await vi.advanceTimersByTimeAsync(3100) })
  await act(async () => { await vi.advanceTimersByTimeAsync(2100) })
  return result.current.activeJob
}

it("carries the merge's not-in-search-yet mark to the dialog", async () => {
  const job = await run(true)
  expect(job?.status).toBe("completed")
  expect(job?.searchPending).toBe(true)
})

it("an unknown mark is not shown as waiting", async () => {
  const job = await run(null)
  expect(job?.status).toBe("completed")
  expect(job?.searchPending).toBe(false)
})

it("tells its caller which entities the merge removed, so a suggestion list can drop them", async () => {
  vi.spyOn(graphAPI, "getEngineJob").mockResolvedValue({ status: "completed", progress: 1 } as never)
  vi.spyOn(graphAPI, "getMergeJob").mockResolvedValue({
    id: "m1", status: "completed", merged_entity_key: "new", recycled_source_keys: ["a", "b"],
    source_entity_keys: ["a", "b"], error_message: null, search_pending: false,
  })
  const onCompleted = vi.fn()
  const { result } = renderHook(() => useMergeTracker({ onCompleted }))
  act(() => result.current.startTracking("e1", "m1", ["a", "b"]))
  await act(async () => { await vi.advanceTimersByTimeAsync(3100) })
  await act(async () => { await vi.advanceTimersByTimeAsync(2100) })
  expect(onCompleted).toHaveBeenCalledWith({ sourceKeys: ["a", "b"], goneKeys: ["a", "b"], mergedKey: "new" })
})
