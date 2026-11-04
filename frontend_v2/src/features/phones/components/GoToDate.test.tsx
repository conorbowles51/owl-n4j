import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { GoToDate } from "./GoToDate"
import { landing } from "./go-to-date"

/** Go to date in the live stream (03 section 6.7, 07 J-4): the day, or the Nearest wording. Synthetic days only. */
const days = [
  { day: "2023-03-10", count: 14 },
  { day: "2023-03-15", count: 3 },
  { day: "2023-03-20", count: 1_200 },
]

describe("Go to date (J-4)", () => {
  it("lands on a day with messages, else names the nearest days before and after with their counts", () => {
    expect(landing(days, "2023-03-15", "in this thread")).toEqual({ kind: "day", day: "2023-03-15" })
    const miss = landing(days, "2023-03-12", "in this thread")
    expect(miss.kind === "none" && miss.words).toBe("No messages on March 12, 2023 in this thread. Nearest: March 10, 2023 (14) and March 15, 2023 (3).")
    const late = landing(days, "2023-04-01", "in these results")
    expect(late.kind === "none" && late.words).toBe("No messages on April 1, 2023 in these results. Nearest: March 20, 2023 (1,200).")
    const none = landing([], "2023-04-01", "in these results")
    expect(none.kind === "none" && none.words).toBe("No messages on April 1, 2023 in these results.")
  })

  it("the control goes to the day, or says why not and offers the nearest days", () => {
    const onGo = vi.fn()
    render(<GoToDate days={days} where="in this thread" open onOpenChange={vi.fn()} onGo={onGo} />)
    const box = screen.getByLabelText("Date to go to")
    fireEvent.change(box, { target: { value: "2023-03-12" } })
    fireEvent.click(screen.getByRole("button", { name: "Go" }))
    expect(onGo).not.toHaveBeenCalled()
    expect(screen.getByRole("status")).toHaveTextContent("No messages on March 12, 2023 in this thread. Nearest: March 10, 2023 (14) and March 15, 2023 (3).")
    fireEvent.click(screen.getByRole("button", { name: "Go to March 15, 2023" }))
    expect(onGo).toHaveBeenLastCalledWith("2023-03-15")
    fireEvent.change(box, { target: { value: "2023-03-20" } })
    fireEvent.click(screen.getByRole("button", { name: "Go" }))
    expect(onGo).toHaveBeenLastCalledWith("2023-03-20")
  })
})
