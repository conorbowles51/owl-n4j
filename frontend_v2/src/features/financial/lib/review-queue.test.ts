import { expect, it } from "vitest"
import { isMoving, isReading } from "./review-queue"

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
