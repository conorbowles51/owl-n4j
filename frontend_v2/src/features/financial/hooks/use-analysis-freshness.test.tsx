import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it } from "vitest"
import type { PropsWithChildren } from "react"
import { useAnalysisFreshness } from "./use-analysis-freshness"

it("refuses an in-flight reading after invalidation and only refreshes the tool that reloads", async () => {
  const client = new QueryClient()
  function wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  const first = renderHook(() => useAnalysisFreshness("case"), { wrapper })
  const second = renderHook(() => useAnalysisFreshness("case"), { wrapper })
  let assertFirst!: () => void, assertSecond!: () => void
  act(() => {
    assertFirst = first.result.current.beginRead()
    assertSecond = second.result.current.beginRead()
  })
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["financial-ledger", "other"] })
  })
  expect(() => assertFirst()).not.toThrow()
  expect(first.result.current.stale).toBe(false)
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["financial-ledger", "case"] })
  })
  expect(() => assertFirst()).toThrow("Payments may have changed while loading")
  expect(() => assertSecond()).toThrow(
    "Payments may have changed while loading"
  )
  expect(first.result.current.stale).toBe(true)
  expect(second.result.current.stale).toBe(true)
  act(() => {
    assertFirst = first.result.current.beginRead()
  })
  expect(first.result.current.stale).toBe(false)
  expect(second.result.current.stale).toBe(true)
  expect(() => assertFirst()).not.toThrow()
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["financial-ledger", "case"] })
  })
  expect(first.result.current.stale).toBe(true)
  expect(() => assertFirst()).toThrow()
})
