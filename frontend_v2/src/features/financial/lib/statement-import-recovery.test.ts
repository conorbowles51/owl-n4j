import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import {
  ImportStillSavingError,
  hasPendingStatementImport,
  importWithReceiptRecovery,
} from "./statement-import-recovery"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))

const endpoint = "/api/financial/statement-import/file?case_id=case"
const request = { rows: [{ excluded: false }, { excluded: true }] }
const receipt = { case_id: "case", evidence_file_id: "file", transaction_count: 1 }
const running = { batch_id: "job", status: "in_progress", outcomes: [] }
const run = (busyRetryDelays?: number[]) =>
  importWithReceiptRecovery({
    endpoint, request, storageKey: "pending", onChecking: vi.fn(), onOperation: vi.fn(),
    ...(busyRetryDelays ? { busyRetryDelays } : {}),
  })
const calls = () => vi.mocked(fetchAPI).mock.calls.map(([url]) => String(url).split("?")[0].split("/").at(-1))

beforeEach(() => {
  vi.useFakeTimers()
  sessionStorage.clear()
  vi.mocked(fetchAPI).mockReset()
})
afterEach(() => vi.useRealTimers())

it("repeats a definite busy submission and returns the receipt once accepted", async () => {
  vi.mocked(fetchAPI)
    .mockResolvedValueOnce({ busy: true, operation: null, receipt: null })
    .mockResolvedValueOnce({ operation: running })
    .mockResolvedValueOnce({ receipt, operation: { ...running, status: "complete" } })
  const result = run([10])
  await vi.runAllTimersAsync()
  await expect(result).resolves.toMatchObject({ result: receipt, expectedCount: 1 })
  expect(calls()).toEqual(["queue-import", "queue-import", "confirm-result"])
})

it("reports a statement that stays busy as nothing imported and forgets the submission", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ busy: true, operation: null, receipt: null })
  const result = run([10, 10])
  const failure = expect(result).rejects.toThrow(/Nothing was imported/)
  await vi.runAllTimersAsync()
  await failure
  await expect(result).rejects.toBeInstanceOf(ApiError)
  expect(calls()).toEqual(["queue-import", "queue-import", "queue-import"])
  expect(hasPendingStatementImport("pending")).toBe(false)
})

it("reports an accepted import that is still saving rather than a failure", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    String(url).includes("/queue-import") ? { operation: running } : { receipt: null, operation: running })
  const result = run()
  const failure = expect(result).rejects.toBeInstanceOf(ImportStillSavingError)
  await vi.runAllTimersAsync()
  await failure
  await expect(result).rejects.toThrow(/Import accepted — still saving/)
  // The submission is kept so background checks can read its receipt later.
  expect(hasPendingStatementImport("pending")).toBe(true)
  expect(calls().filter((call) => call === "queue-import")).toHaveLength(1)
})

it("keeps the uncertain-write message when no accepted import was seen", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (String(url).includes("/queue-import")) throw new ApiError("Request timed out", 408)
    return { receipt: null, operation: null }
  })
  const result = run()
  const failure = expect(result).rejects.toThrow(/has not returned a final receipt yet/)
  await vi.runAllTimersAsync()
  await failure
})
