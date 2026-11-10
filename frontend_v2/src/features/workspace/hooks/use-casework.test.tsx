import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { caseworkAPI, type CaseworkListParams } from "../casework-api"
import { useCaseworkEntries, useCreateCaseworkEntry, useUpdateCaseworkEntry } from "./use-casework"
import { notebookAPI } from "@/features/notebook/api"
import { useTargetNotebookNotes } from "@/features/notebook/hooks/use-notebook"

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
    ({ caseId }: { caseId: string }) => useCaseworkEntries(caseId, {}),
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
  vi.spyOn(caseworkAPI, "list").mockImplementation((_caseId: string, params?: CaseworkListParams) =>
    params?.q === "cash"
      ? (new Promise((resolve) => { finishSecond = resolve }) as never)
      : Promise.resolve(first as never),
  )
  const { result, rerender } = renderHook(
    ({ q }: { q?: string }) => useCaseworkEntries("case-a", { q }),
    { initialProps: { q: undefined as string | undefined }, wrapper: wrapper() },
  )
  await waitFor(() => expect(result.current.data).toEqual(first))
  rerender({ q: "cash" })
  expect(result.current.data).toEqual(first)
  expect(result.current.isPlaceholderData).toBe(true)
  finishSecond({ entries: [], total: 0 })
  await waitFor(() => expect(result.current.isPlaceholderData).toBe(false))
})

it("a note saved or edited in casework shows on the entity's Notebook card without waiting for the cache (BUG-007)", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 120_000 } } })
  const w = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  let notes: { id: string }[] = []
  const listTarget = vi.spyOn(notebookAPI, "listTargetNotes").mockImplementation(async () => ({ notes, total: notes.length }) as never)
  vi.spyOn(caseworkAPI, "create").mockImplementation(async () => { notes = [{ id: "n-1" }]; return { id: "n-1" } as never })
  vi.spyOn(caseworkAPI, "update").mockImplementation(async () => { notes = [{ id: "n-1" }, { id: "n-2" }]; return { id: "n-1" } as never })
  const card = renderHook(() => useTargetNotebookNotes("case-a", "entity" as never, "e-1"), { wrapper: w })
  await waitFor(() => expect(card.result.current.data).toEqual({ notes: [], total: 0 }))
  const create = renderHook(() => useCreateCaseworkEntry("case-a"), { wrapper: w })
  await create.result.current.mutateAsync({ entry_type: "note", body: "x" } as never)
  await waitFor(() => expect(card.result.current.data).toEqual({ notes: [{ id: "n-1" }], total: 1 }))
  const update = renderHook(() => useUpdateCaseworkEntry("case-a"), { wrapper: w })
  await update.result.current.mutateAsync({ entryId: "n-1", input: { body: "y" } as never })
  await waitFor(() => expect(card.result.current.data?.total).toBe(2))
  expect(listTarget).toHaveBeenCalledTimes(3)
})

it("refreshes open dossiers when a casework reference is changed", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  const w = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  let references = 0
  const detail = renderHook(() => useQuery({ queryKey: ["dossiers", "detail", "dossier-1"], queryFn: async () => ({ references }) }), { wrapper: w })
  const list = renderHook(() => useQuery({ queryKey: ["dossiers", "list", "case-a", {}], queryFn: async () => ({ references }) }), { wrapper: w })
  await waitFor(() => expect(detail.result.current.data?.references).toBe(0))
  await waitFor(() => expect(list.result.current.data?.references).toBe(0))
  vi.spyOn(caseworkAPI, "update").mockImplementation(async () => { references = 1; return { id: "n-1" } as never })
  const update = renderHook(() => useUpdateCaseworkEntry("case-a"), { wrapper: w })
  await update.result.current.mutateAsync({ entryId: "n-1", input: { expected_version: 1, body: "Updated" } })
  await waitFor(() => expect(detail.result.current.data?.references).toBe(1))
  expect(list.result.current.data?.references).toBe(1)
})
