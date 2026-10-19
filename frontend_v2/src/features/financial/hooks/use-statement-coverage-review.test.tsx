import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useStatementCoverageReview } from "./use-statement-coverage-review"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
afterEach(() => vi.resetAllMocks())
const input = {
  expected_revision: "a".repeat(64),
  statement_id: null,
  currency: "EUR",
  institution: "Test Bank",
  account_number: "123",
  period_start: "2023-01-01",
  period_end: "2023-12-31",
}
const output = {
  case_id: "case",
  evidence_file_id: "file",
  available: true,
  revision: "b".repeat(64),
  candidates: [],
}

it("discards old responses when an account is changed and sends only statement details", async () => {
  let resolveOld: (value: unknown) => void = () => {}
  vi.mocked(fetchAPI)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        })
    )
    .mockResolvedValueOnce(output)
  const hook = renderHook(
    ({ account }) =>
      useStatementCoverageReview("case", "file", {
        ...input,
        account_number: account,
      }),
    { initialProps: { account: "123" } }
  )
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  hook.rerender({ account: "456" })
  expect(hook.result.current.pending).toBe(true)
  await act(async () => resolveOld({ ...output, revision: "old" }))
  expect(hook.result.current.data).toBeUndefined()
  await waitFor(() =>
    expect(hook.result.current.data?.revision).toBe(output.revision)
  )
  expect(vi.mocked(fetchAPI).mock.calls[1][1]?.body).toEqual({
    ...input,
    account_number: "456",
  })
})

it("retries failed requests and refuses another case's response", async () => {
  vi.mocked(fetchAPI)
    .mockRejectedValueOnce(Error("Connection interrupted"))
    .mockResolvedValueOnce({ ...output, case_id: "elsewhere" })
    .mockResolvedValueOnce(output)
  const hook = renderHook(() =>
    useStatementCoverageReview("case", "file", input)
  )
  await waitFor(() =>
    expect(hook.result.current.error).toBe("Connection interrupted")
  )
  act(() => hook.result.current.retry())
  await waitFor(() => expect(hook.result.current.error).toBeTruthy())
  expect(hook.result.current.data).toBeUndefined()
  act(() => hook.result.current.retry())
  await waitFor(() =>
    expect(hook.result.current.data?.revision).toBe(output.revision)
  )
})
