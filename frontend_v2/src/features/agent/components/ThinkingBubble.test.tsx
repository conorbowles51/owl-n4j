import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ThinkingBubble } from "./ThinkingBubble"

afterEach(() => vi.useRealTimers())

// Live 8 Nov 2026: a 5 min 14 s run showed a bare spinner and looked stuck.
it("shows what the run is doing, steps done and time so far, ticking every second, with Cancel", () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-11-08T22:24:00Z"))
  const cancel = vi.fn()
  render(
    <ThinkingBubble
      status="Checking accounts held by Jose Alejandro Reyes Zeind"
      startedAt={Date.now() - 99_000}
      stepsDone={3}
      onCancel={cancel}
    />
  )
  const status = screen.getByRole("status")
  expect(status).toHaveTextContent("Checking accounts held by Jose Alejandro Reyes Zeind")
  expect(status).toHaveTextContent("3 steps done · 1 min 39 s")
  act(() => {
    vi.advanceTimersByTime(2000)
  })
  expect(status).toHaveTextContent("1 min 41 s")
  expect(status).toHaveTextContent("keeps running if you open another page")
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(cancel).toHaveBeenCalledTimes(1)
})

it("shows no invented time or steps when they are not known", () => {
  render(<ThinkingBubble status={null} />)
  expect(screen.getByRole("status")).toHaveTextContent("Working through the case data")
  expect(screen.getByRole("status")).not.toHaveTextContent(/steps? done| s$/)
})
