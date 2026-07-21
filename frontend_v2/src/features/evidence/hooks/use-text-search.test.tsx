import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useDebouncedValue } from "./use-text-search"

describe("useDebouncedValue", () => {
  afterEach(() => vi.useRealTimers())

  it("waits 350 ms before publishing a changed search query", () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 350),
      { initialProps: { value: "ab" } }
    )

    rerender({ value: "account number" })
    act(() => vi.advanceTimersByTime(349))
    expect(result.current).toBe("ab")

    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe("account number")
  })
})
