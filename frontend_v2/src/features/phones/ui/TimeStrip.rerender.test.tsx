import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

// The record page re-renders the conversation list as each window of messages arrives; the time strip under it used
// to name every day of the scope again (one title per bar) on each of those renders.
const words = vi.hoisted(() => ({ calls: 0 }))
vi.mock("./strip-words", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./strip-words")>()
  return {
    ...actual,
    dayWords: (date: string) => {
      words.calls += 1
      return actual.dayWords(date)
    },
  }
})

import { dayWords } from "./strip-words"
import { TimeStrip, type StripDay } from "./TimeStrip"

const days: StripDay[] = Array.from({ length: 400 }, (_, i) => {
  const d = new Date(Date.UTC(2025, 0, 1 + i))
  return { date: d.toISOString().slice(0, 10), count: i % 7 === 0 ? null : (i * 37) % 1500 }
})

describe("TimeStrip on a page that re-renders", () => {
  it("does not draw its bars again when only the page around it re-renders", () => {
    const first = vi.fn()
    const { rerender } = render(<TimeStrip days={days} zone="UTC" onPickDay={first} />)
    expect(words.calls).toBeGreaterThanOrEqual(days.length)

    words.calls = 0
    const second = vi.fn()
    rerender(<TimeStrip days={days} zone="UTC" onPickDay={second} />)
    // only the slider's own words for the day under the cursor
    expect(words.calls).toBeLessThanOrEqual(1)

    // a bar pressed after the re-render goes to the newest handler
    fireEvent.click(screen.getByText(`${dayWords(days[3].date)}: ${days[3].count!.toLocaleString("en-US")} messages`).parentElement!)
    expect(second).toHaveBeenCalledWith(days[3].date)
    expect(first).not.toHaveBeenCalled()
  })

  it("names each day and count exactly as before", () => {
    render(<TimeStrip days={days} zone="UTC" onPickDay={() => {}} />)
    for (const d of [days[0], days[1], days[199], days[399]]) {
      const words = new Date(`${d.date}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
      const text = d.count === null ? `${words}: no data` : `${words}: ${d.count.toLocaleString("en-US")} messages`
      expect(screen.getByText(text)).toBeInTheDocument()
    }
    expect(dayWords("not a date")).toBe(new Date("not a dateT12:00:00Z").toLocaleDateString("en-US"))
  })
})
