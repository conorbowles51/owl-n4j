import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

/** Find in these results (03 section 3.1 rule 4, 07 section 4.8, UX-2), with the server stubbed. */
const api = vi.hoisted(() => ({ streamFind: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { FindInResults } from "./FindInResults"

const matches = [
  { day: "2023-03-14", offset: 3, event_uid: "e1" },
  { day: "2023-03-14", offset: 1800, event_uid: "e2" },
  { day: null, offset: 0, event_uid: "e3" },
]

describe("Find in these results", () => {
  it("the first Ctrl/Cmd+F opens it, the server's whole-result matches are stepped through, the second press is the browser's", async () => {
    api.streamFind.mockResolvedValue({ total: 3, matches })
    const onGo = vi.fn()
    const onQuery = vi.fn()
    render(<FindInResults filter={{ case_id: "c1" } as never} snapshot="s1" onGo={onGo} onQuery={onQuery} />)
    const first = new KeyboardEvent("keydown", { key: "f", ctrlKey: true, cancelable: true })
    act(() => {
      window.dispatchEvent(first)
    })
    expect(first.defaultPrevented).toBe(true)
    const box = await screen.findByRole("textbox", { name: "Find in these results" })
    await waitFor(() => expect(document.activeElement).toBe(box))
    const second = new KeyboardEvent("keydown", { key: "f", metaKey: true, cancelable: true })
    act(() => {
      window.dispatchEvent(second)
    })
    expect(second.defaultPrevented).toBe(false)
    fireEvent.change(box, { target: { value: "synthetic" } })
    fireEvent.keyDown(box, { key: "Enter" })
    expect(await screen.findByText("Match 1 of 3")).toBeInTheDocument()
    expect(api.streamFind).toHaveBeenCalledWith({ case_id: "c1" }, "s1", "synthetic")
    expect(onGo).toHaveBeenLastCalledWith(matches[0])
    expect(onQuery).toHaveBeenLastCalledWith("synthetic")
    fireEvent.keyDown(box, { key: "Enter" })
    expect(screen.getByText("Match 2 of 3")).toBeInTheDocument()
    expect(onGo).toHaveBeenLastCalledWith(matches[1]) // a row far outside any window in view
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true })
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true })
    expect(screen.getByText("Match 3 of 3")).toBeInTheDocument()
    expect(api.streamFind).toHaveBeenCalledTimes(1)
  })

  it("says when nothing matches, and shows the server's refusal of a search too large to list", async () => {
    api.streamFind.mockResolvedValueOnce({ total: 0, matches: [] })
    render(<FindInResults filter={{ case_id: "c1" } as never} snapshot="s1" onGo={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: "Find in these results" }))
    const box = await screen.findByRole("textbox", { name: "Find in these results" })
    fireEvent.change(box, { target: { value: "nowhere" } })
    fireEvent.keyDown(box, { key: "Enter" })
    expect(await screen.findByText("No match in these results")).toBeInTheDocument()
    api.streamFind.mockRejectedValueOnce(new Error("12,001 matches is more than one search lists (10,000). Add a word or a filter to narrow it; nothing was listed."))
    fireEvent.change(box, { target: { value: "a" } })
    fireEvent.keyDown(box, { key: "Enter" })
    expect(await screen.findByRole("alert")).toHaveTextContent(/12,001 matches|could not be run/)
  })
})
