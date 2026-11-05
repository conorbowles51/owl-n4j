import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { ThreadRow } from "@/features/phones/schemas"
import { ThreadList } from "./ThreadList"

/** Synthetic threads only. Budget: a phone's whole thread list is never in the page at once (lx-convspeed). */
const thread = (i: number, phone = "e1"): ThreadRow => ({
  thread_key: `chat:${i}`, phone: { extraction_id: phone, label: phone === "e1" ? "C1" : "C2" }, app: "SyntheticApp", chat_type: null, thread_kind: "chat", title: `Synthetic ${i}`,
  participants: [], participant_count: 2, first_instant: null, last_instant: null, last_full: "", event_count: 3, event_count_total: 3,
  deleted_count: 0, has_unreadable: false, review: null,
})
const many = Array.from({ length: 942 }, (_, i) => thread(i))
const list = (threads: ThreadRow[], extra: Partial<Parameters<typeof ThreadList>[0]> = {}) =>
  render(<div style={{ height: 800, display: "flex", flexDirection: "column" }}><ThreadList threads={threads} total={threads.length} open={null} multiPhone={false} byName={false} onPick={vi.fn()} {...extra} /></div>)

describe("ThreadList", () => {
  it("puts only the rows in view in the page, and names the whole list", () => {
    list(many)
    const box = screen.getByRole("listbox", { name: "Threads (942)" })
    const rows = within(box).getAllByRole("option")
    expect(rows.length).toBeGreaterThan(5)
    expect(rows.length).toBeLessThanOrEqual(40)
    expect(rows[0]).toHaveAttribute("aria-setsize", "942")
    expect(rows[0]).toHaveAttribute("aria-posinset", "1")
    // the sizer holds every thread, so the scrollbar is the whole list
    expect(box.style.height).toBe(`${942 * 65}px`)
  })

  it("reaches the last thread by scrolling", () => {
    list(many)
    const scroller = screen.getByTestId("thread-scroll")
    fireEvent.scroll(scroller, { target: { scrollTop: 942 * 65 } })
    const last = screen.getByRole("option", { name: /Synthetic 941/ })
    expect(last).toHaveAttribute("aria-posinset", "942")
  })

  it("draws a short list whole, marks the open thread and opens on click and Enter", () => {
    const onPick = vi.fn()
    list([thread(0), thread(1), thread(2)], { open: "chat:1", onPick })
    expect(screen.getAllByRole("option")).toHaveLength(3)
    const open = screen.getByRole("option", { name: /Synthetic 1/ })
    expect(open).toHaveAttribute("aria-selected", "true")
    fireEvent.click(screen.getByRole("option", { name: /Synthetic 2/ }))
    fireEvent.keyDown(screen.getByRole("option", { name: /Synthetic 0/ }), { key: "Enter" })
    expect(onPick.mock.calls).toEqual([["chat:2"], ["chat:0"]])
  })

  it("keeps the phone headings when sorted by name across phones", () => {
    list([thread(0), thread(1), thread(2, "e2")], { multiPhone: true, byName: true })
    expect(screen.getAllByText("C1").length).toBeGreaterThan(0)
    expect(screen.getAllByText("C2").length).toBeGreaterThan(0)
  })
})
