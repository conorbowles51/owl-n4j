import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { findSimilarEntitiesStream, type SimilarEntitiesStreamCallbacks } from "../api"
import { SCAN_STOPPED, useSimilarEntities } from "./use-similar-entities"

vi.mock("../api", () => ({ findSimilarEntitiesStream: vi.fn() }))

describe("useSimilarEntities", () => {
  let callbacks: SimilarEntitiesStreamCallbacks
  const close = vi.fn()

  beforeEach(() => {
    close.mockReset()
    vi.mocked(findSimilarEntitiesStream).mockImplementation((_c, _o, cb) => {
      callbacks = cb
      return close
    })
  })

  it("says so when the server stops the scan", () => {
    const { result } = renderHook(() => useSimilarEntities("case-a"))
    act(() => result.current.startScan({}))
    act(() => callbacks.onCancelled?.())
    expect(result.current.error).toBe(SCAN_STOPPED)
    expect(result.current.isScanning).toBe(false)
  })

  it("stays silent when the person cancels", () => {
    const { result } = renderHook(() => useSimilarEntities("case-a"))
    act(() => result.current.startScan({}))
    act(() => result.current.cancel())
    expect(close).toHaveBeenCalled()
    expect(result.current.error).toBeNull()
    expect(result.current.isScanning).toBe(false)
  })

  // GR-02: after one merge the list kept offering the merged-away entity, and the next merge failed with "Entity not found".
  it("after a merge drops every pair naming a merged-away entity and rescans with the same filters", () => {
    const pair = (a: string, b: string) => ({ entity1: { key: a, name: a, type: "Person" }, entity2: { key: b, name: b, type: "Person" }, similarity: 0.9 })
    const { result } = renderHook(() => useSimilarEntities("case-a"))
    act(() => result.current.startScan({ entityTypes: ["Person"], similarityThreshold: 0.8 }))
    act(() => callbacks.onComplete({ limited_results: [pair("a", "b"), pair("b", "c"), pair("d", "e")], total_pairs: 3 } as never))
    expect(result.current.results).toHaveLength(3)

    act(() => result.current.afterMerge(["a", "b"]))
    expect(result.current.results.map((p) => `${p.key1}-${p.key2}`)).toEqual(["d-e"])
    expect(vi.mocked(findSimilarEntitiesStream)).toHaveBeenLastCalledWith("case-a", { entityTypes: ["Person"], similarityThreshold: 0.8 }, expect.anything())
    // the pruned list stays on screen while the rescan runs
    expect(result.current.results).toHaveLength(1)

    // a rescan that read the graph before the merge finished still never offers a removed entity
    act(() => callbacks.onComplete({ limited_results: [pair("b", "c"), pair("m", "c"), pair("d", "e")], total_pairs: 3 } as never))
    expect(result.current.results.map((p) => `${p.key1}-${p.key2}`)).toEqual(["m-c", "d-e"])
  })
})
