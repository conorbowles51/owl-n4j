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
})
