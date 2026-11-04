/**
 * The account filters read the whole account directory in one request (d5b330d1: three requests of 100 accounts,
 * each waiting for the one before, 1.5-3.5 s apart on a loaded browser), and still page on if the answer says more
 * accounts follow.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { useLedgerAccountDirectory } from "./use-ledger-account-directory"

const CASE = "10000000-0000-4000-8000-000000000001"
const calls = vi.hoisted(() => [] as string[])
const answer = vi.hoisted(() => ({ more: false }))
const account = (n: number) => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  display_label: `Account ${n}`,
  identifier: null,
  holder: null,
  institution: null,
  currency: "USD",
  provisional: false,
})
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) => {
    calls.push(url)
    const query = new URLSearchParams(url.split("?")[1])
    const offset = Number(query.get("offset"))
    const items = query.get("whole") === "true" ? [account(1), account(2), account(3)] : [account(offset + 1)]
    return {
      case_id: CASE,
      has_more: answer.more && offset === 0,
      pending_holders: [],
      pending_directory_truncated: false,
      items,
    }
  }),
}))

afterEach(() => {
  calls.length = 0
  answer.more = false
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
)

it("reads every account in one request", async () => {
  const { result } = renderHook(() => useLedgerAccountDirectory(CASE), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(calls).toHaveLength(1)
  expect(calls[0]).toContain("whole=true")
  expect(result.current.data!.items.map((a) => a.display_label)).toEqual(["Account 1", "Account 2", "Account 3"])
})

it("pages on when the answer says more accounts follow", async () => {
  answer.more = true
  const { result } = renderHook(() => useLedgerAccountDirectory(CASE), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(calls).toHaveLength(2)
  expect(calls[1]).toContain("offset=3")
  expect(calls[1]).not.toContain("whole")
  expect(result.current.data!.items).toHaveLength(4)
})
