import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useStatementChecks } from "./use-statement-checks"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
afterEach(() => {
  vi.useRealTimers()
  vi.resetAllMocks()
})
const input = {
  expected_revision: "a".repeat(64),
  statement_id: null,
  currency: "EUR",
  rows: [],
}
const output = {
  revision: input.expected_revision,
  checks_revision: "b".repeat(64),
  applied: false,
  checks: [{ kind: "closing_balance", status: "matches" }],
}

it("ignores an earlier response and disables readiness immediately after an edit", async () => {
  let oldResolve: (value: unknown) => void = () => {}
  vi.mocked(fetchAPI)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          oldResolve = resolve
        })
    )
    .mockResolvedValueOnce(output)
  const hook = renderHook(
    ({ rows }) => useStatementChecks("case", "file", { ...input, rows }),
    { initialProps: { rows: [] as unknown[] } }
  )
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  hook.rerender({ rows: [{ id: "row", amount_minor: "100" }] })
  expect(hook.result.current.pending).toBe(true)
  await act(async () =>
    oldResolve({
      ...output,
      checks: [{ kind: "closing_balance", status: "difference" }],
    })
  )
  expect(hook.result.current.checks).toEqual([])
  await waitFor(() => expect(hook.result.current.pending).toBe(false))
  expect(hook.result.current.checks[0].status).toBe("matches")
  hook.rerender({ rows: [{ id: "row", amount_minor: "200" }] })
  expect(hook.result.current.pending).toBe(true)
  expect(hook.result.current.checks).toEqual([])
})

it("shows a failed check, supports retry, and rejects another source revision", async () => {
  vi.mocked(fetchAPI)
    .mockRejectedValueOnce(Error("Connection interrupted"))
    .mockResolvedValueOnce({ ...output, revision: "changed" })
    .mockResolvedValueOnce(output)
  const hook = renderHook(() => useStatementChecks("case", "file", input))
  await waitFor(() =>
    expect(hook.result.current.error).toBe("Connection interrupted")
  )
  act(() => hook.result.current.retry())
  expect(hook.result.current.pending).toBe(true)
  await waitFor(() =>
    expect(hook.result.current.error).toContain("reading changed")
  )
  act(() => hook.result.current.retry())
  await waitFor(() =>
    expect(hook.result.current.revision).toBe(output.checks_revision)
  )
})
