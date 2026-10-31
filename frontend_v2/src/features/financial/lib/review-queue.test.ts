import { afterEach, expect, it, vi } from "vitest"
import { fetchReviewQueue, isMoving, isReading } from "./review-queue"

afterEach(() => vi.unstubAllGlobals())

it("keeps reading the queue while statements are checked again or saved, and stops when nothing moves", () => {
  expect(isMoving({ rechecking: 2, saving: 0 })).toBe(true)
  expect(isMoving({ rechecking: 0, saving: 5 })).toBe(true)
  expect(isMoving({ rechecking: 0, saving: 0 })).toBe(false)
  expect(isMoving(undefined)).toBe(false)
  expect(
    isReading({
      files_total: 0,
      files_done: 0,
      files_reading: 0,
      paused: false,
      files_waiting_to_start: 0,
      unread_statement_files: 0,
    })
  ).toBe(false)
})

it("reads the whole queue for an action fresh, never the previous queue shown while the current one is built", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }))
  vi.stubGlobal("fetch", fetch)
  await fetchReviewQueue("c1", ["f1"]).catch(() => undefined)
  const url = new URL(fetch.mock.calls[0][0], "http://x")
  expect(url.searchParams.get("fresh")).toBe("1")
  expect(url.searchParams.getAll("file_id")).toEqual(["f1"])
})
