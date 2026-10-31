import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { caseworkAPI } from "../casework-api"
import { useCaseworkEntries } from "./use-casework"

afterEach(() => vi.restoreAllMocks())

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

it("never shows another case's entries while this case's list loads", async () => {
  const listA = { entries: [{ id: "a-1" }], total: 1 }
  let finishB: (value: unknown) => void = () => {}
  vi.spyOn(caseworkAPI, "list").mockImplementation((caseId: string) =>
    caseId === "case-a"
      ? Promise.resolve(listA as never)
      : (new Promise((resolve) => { finishB = resolve }) as never),
  )
  const { result, rerender } = renderHook(
    ({ caseId }: { caseId: string }) => useCaseworkEntries(caseId, { limit: 20 } as never),
    { initialProps: { caseId: "case-a" }, wrapper: wrapper() },
  )
  await waitFor(() => expect(result.current.data).toEqual(listA))

  rerender({ caseId: "case-b" })
  expect(result.current.data).toBeUndefined()
  expect(result.current.isPending).toBe(true)

  const listB = { entries: [{ id: "b-1" }], total: 1 }
  finishB(listB)
  await waitFor(() => expect(result.current.data).toEqual(listB))
})

it("keeps the same case's list up while a filter reloads", async () => {
  const first = { entries: [{ id: "a-1" }], total: 1 }
  let finishSecond: (value: unknown) => void = () => {}
  vi.spyOn(caseworkAPI, "list").mockImplementation((_caseId: string, params: { kind?: string }) =>
    params.kind === "finding"
      ? (new Promise((resolve) => { finishSecond = resolve }) as never)
      : Promise.resolve(first as never),
  )
  const { result, rerender } = renderHook(
    ({ kind }: { kind?: string }) => useCaseworkEntries("case-a", { kind } as never),
    { initialProps: { kind: undefined as string | undefined }, wrapper: wrapper() },
  )
  await waitFor(() => expect(result.current.data).toEqual(first))
  rerender({ kind: "finding" })
  expect(result.current.data).toEqual(first)
  expect(result.current.isPlaceholderData).toBe(true)
  finishSecond({ entries: [], total: 0 })
  await waitFor(() => expect(result.current.isPlaceholderData).toBe(false))
})
