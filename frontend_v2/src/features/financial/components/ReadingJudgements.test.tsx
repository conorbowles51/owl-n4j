vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

import { act, render } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReadingJudgements } from "./JudgementCalls"

afterEach(() => vi.useRealTimers())

it("the holder goes to the preview once typing settles, not on every keystroke", async () => {
  vi.useFakeTimers()
  vi.mocked(fetchAPI).mockResolvedValue({ items: [] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = (holder: string) => (
    <QueryClientProvider client={client}>
      <ReadingJudgements caseId="c1" statementId="k1" revision="r1" currency="USD" readingRows={[]} reviewRows={[]}
        fileId="f1" holder={holder} />
    </QueryClientProvider>
  )
  const { rerender } = render(view("E"))
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
  rerender(view("ER"))
  rerender(view("ERICA HOPPER"))
  await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  const holders = vi.mocked(fetchAPI).mock.calls.map(([, options]) => (options as { body: { holder?: string } }).body.holder)
  expect(holders).toEqual(["E", "ERICA HOPPER"])
})
