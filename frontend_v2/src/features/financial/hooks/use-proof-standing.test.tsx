import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { proofStanding } from "@/test/proof-standing-fixture"
import { useProofStanding } from "./use-proof-standing"
import { useIngestFile } from "./use-ledger-ingest"

const fetchMock = vi.fn<typeof fetch>()
const json = (data: unknown) =>
  new Response(JSON.stringify(data), { status: 200 })
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return { client, wrapper: Wrapper }
}
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

it("does not request a census without a case", () => {
  renderHook(() => useProofStanding(undefined), setup())
  expect(fetchMock).not.toHaveBeenCalled()
})
it("requests only the case, and retains the full census", async () => {
  fetchMock.mockResolvedValueOnce(json(proofStanding()))
  const { result } = renderHook(() => useProofStanding("case-1"), setup())
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(String(fetchMock.mock.calls[0][0])).toBe(
    "/api/financial/proof-standing?case_id=case-1"
  )
  expect(result.current.data).toEqual(proofStanding())
})
it("does not display the previous case while the next is loading", async () => {
  fetchMock.mockResolvedValueOnce(json(proofStanding()))
  const { result, rerender } = renderHook(({ id }) => useProofStanding(id), {
    ...setup(),
    initialProps: { id: "case-1" },
  })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  rerender({ id: "case-2" })
  expect(result.current.data).toBeUndefined()
  await act(async () => {
    resolve(json(proofStanding("case-2")))
  })
  await waitFor(() => expect(result.current.data?.case_id).toBe("case-2"))
})
it("treats a census from another case as an error", async () => {
  fetchMock.mockResolvedValueOnce(json(proofStanding("other-case")))
  const { result } = renderHook(() => useProofStanding("case-1"), setup())
  await waitFor(() => expect(result.current.isError).toBe(true))
  expect(result.current.data).toBeUndefined()
})
it.each([true, false])(
  "refreshes a mounted census only when ingestion stored records: %s",
  async (stored) => {
    let reads = 0
    fetchMock.mockImplementation(async (url) => {
      if (String(url).includes("proof-standing")) {
        reads++
        return json(proofStanding())
      }
      return json({ stored, outcome: stored ? "ingested" : "already_ingested" })
    })
    const { wrapper } = setup()
    const { result } = renderHook(
      () => ({
        census: useProofStanding("case-1"),
        ingest: useIngestFile("case-1"),
      }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.census.isSuccess).toBe(true))
    await act(async () => {
      await result.current.ingest.mutateAsync({
        fileId: "file-a",
        windowStart: "2020-01-01",
        windowEnd: "2026-12-31",
      })
    })
    await waitFor(() => expect(reads).toBe(stored ? 2 : 1))
  }
)

it("invalidates the case that started ingestion when navigation happens before completion", async () => {
  const { client, wrapper } = setup()
  client.setQueryData(["financial-proof-standing", "case-1"], proofStanding())
  client.setQueryData(
    ["financial-proof-standing", "case-2"],
    proofStanding("case-2")
  )
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  const { result, rerender } = renderHook(({ id }) => useIngestFile(id), {
    wrapper,
    initialProps: { id: "case-1" },
  })
  let pending!: Promise<unknown>
  act(() => {
    pending = result.current.mutateAsync({
      fileId: "file-a",
      windowStart: "2020-01-01",
      windowEnd: "2026-12-31",
    })
  })
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  rerender({ id: "case-2" })
  await act(async () => {
    resolve(json({ stored: true, outcome: "ingested" }))
    await pending
  })
  expect(
    client.getQueryState(["financial-proof-standing", "case-1"])?.isInvalidated
  ).toBe(true)
  expect(
    client.getQueryState(["financial-proof-standing", "case-2"])?.isInvalidated
  ).toBe(false)
})
